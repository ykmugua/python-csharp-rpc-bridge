using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace ModulePlatform.PyfRpc;

/// <summary>Starts a Python backend and exchanges framed JSON RPC messages over standard streams.</summary>
public sealed class StdioRpcClient : IDisposable
{
    private readonly string _exePath;
    private readonly string[] _arguments;
    private readonly int _defaultTimeoutMs;
    private readonly int _breakerThreshold;
    private readonly TimeSpan _breakerWindow;
    private readonly object _lifecycleLock = new();
    private readonly object _writeLock = new();
    private readonly object _breakerLock = new();
    private readonly ConcurrentDictionary<long, TaskCompletionSource<JsonObject>> _pending = new();
    private readonly Queue<DateTime> _crashes = new();

    private Process? _process;
    private Stream? _stdin;
    private Thread? _reader;
    private long _nextId;
    private volatile bool _running;
    private volatile bool _disposed;
    private string _stderrTail = string.Empty;

    /// <summary>Creates a client for a backend executable and optional command-line arguments.</summary>
    /// <param name="exePath">The Python executable or standalone backend path.</param>
    /// <param name="defaultTimeoutMs">The default timeout for an RPC call, in milliseconds.</param>
    /// <param name="breakerThreshold">The number of crashes that opens the restart circuit.</param>
    /// <param name="breakerWindow">The time window used to count backend crashes.</param>
    /// <param name="arguments">Optional arguments passed to the executable.</param>
    public StdioRpcClient(
        string exePath,
        int defaultTimeoutMs = 30_000,
        int breakerThreshold = 3,
        TimeSpan? breakerWindow = null,
        IEnumerable<string>? arguments = null)
    {
        if (string.IsNullOrWhiteSpace(exePath))
            throw new ArgumentException("A backend executable path is required.", nameof(exePath));
        if (defaultTimeoutMs <= 0)
            throw new ArgumentOutOfRangeException(nameof(defaultTimeoutMs));
        if (breakerThreshold <= 0)
            throw new ArgumentOutOfRangeException(nameof(breakerThreshold));

        _exePath = exePath;
        _arguments = arguments?.ToArray() ?? Array.Empty<string>();
        _defaultTimeoutMs = defaultTimeoutMs;
        _breakerThreshold = breakerThreshold;
        _breakerWindow = breakerWindow ?? TimeSpan.FromSeconds(60);
        if (_breakerWindow <= TimeSpan.Zero)
            throw new ArgumentOutOfRangeException(nameof(breakerWindow));
    }

    /// <summary>Starts the backend process and its response reader.</summary>
    public void Start()
    {
        lock (_lifecycleLock)
        {
            if (_disposed)
                throw new ObjectDisposedException(nameof(StdioRpcClient));
            Process? staleProcess;
            lock (_writeLock)
            {
                if (_running)
                    return;
                staleProcess = _process;
                _process = null;
                _stdin = null;
                _reader = null;
            }
            if (staleProcess is not null)
                RetireProcess(staleProcess);
            if (IsBreakerOpen())
                throw new RpcException("BackendCrashed", "Restart circuit breaker is open.");

            var startInfo = new ProcessStartInfo(_exePath)
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            startInfo.Arguments = string.Join(" ", _arguments.Select(QuoteArgument));
            var process = new Process { StartInfo = startInfo };
            process.ErrorDataReceived += (_, eventArgs) =>
            {
                if (eventArgs.Data is not null)
                    AppendStderr(eventArgs.Data);
            };

            var processStarted = false;
            try
            {
                if (!process.Start())
                    throw new RpcException("BackendCrashed", $"Failed to start backend: {_exePath}");
                processStarted = true;
                process.BeginErrorReadLine();
                _stderrTail = string.Empty;
                var reader = new Thread(() => ReadLoop(process, process.StandardOutput.BaseStream))
                {
                    IsBackground = true,
                    Name = "PyfRpc read loop"
                };
                lock (_writeLock)
                {
                    _stdin = process.StandardInput.BaseStream;
                    _process = process;
                    _reader = reader;
                    _running = true;
                }
                reader.Start();
            }
            catch (Exception exception)
            {
                lock (_writeLock)
                {
                    _running = false;
                    _stdin = null;
                    _process = null;
                    _reader = null;
                }
                if (processStarted)
                    RetireProcess(process);
                else
                    process.Dispose();
                if (exception is RpcException)
                    throw;
                throw new RpcException("BackendCrashed", $"Failed to start backend: {_exePath}", innerException: exception);
            }
        }
    }

    /// <summary>Stops and starts the backend process.</summary>
    public void Restart()
    {
        Stop();
        Start();
    }

    /// <summary>Sends a request and returns its JSON result.</summary>
    /// <param name="method">The Python function or class-method name.</param>
    /// <param name="parameters">The JSON object containing named arguments.</param>
    /// <param name="timeoutMs">An optional per-call timeout in milliseconds.</param>
    /// <param name="instanceId">An optional Python class instance ID.</param>
    /// <returns>The response result, or <see langword="null"/> for a null result.</returns>
    public JsonNode? InvokeRaw(
        string method,
        JsonNode? parameters,
        int? timeoutMs = null,
        string? instanceId = null)
    {
        if (string.IsNullOrWhiteSpace(method))
            throw new ArgumentException("An RPC method name is required.", nameof(method));
        if (instanceId is not null && string.IsNullOrWhiteSpace(instanceId))
            throw new ArgumentException("An instance ID cannot be empty.", nameof(instanceId));
        var timeout = timeoutMs ?? _defaultTimeoutMs;
        if (timeout <= 0)
            throw new ArgumentOutOfRangeException(nameof(timeoutMs));

        var id = Interlocked.Increment(ref _nextId);
        var completion = new TaskCompletionSource<JsonObject>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        if (!_pending.TryAdd(id, completion))
            throw new InvalidOperationException("RPC request id collision.");

        try
        {
            try
            {
                var frame = Protocol.EncodeFrame(id, method, parameters, instanceId);
                lock (_writeLock)
                {
                    if (_disposed)
                        throw new ObjectDisposedException(nameof(StdioRpcClient));
                    if (!_running || _stdin is null)
                        throw new RpcException("NotRunning", "The Python backend is not running.");
                    _stdin.Write(frame, 0, frame.Length);
                    _stdin.Flush();
                }
            }
            catch (ObjectDisposedException)
            {
                throw;
            }
            catch (RpcException)
            {
                throw;
            }
            catch (Exception exception) when (exception is IOException or ObjectDisposedException or InvalidOperationException)
            {
                var writeFailure = new RpcException("WriteFailed", "Failed to write to the Python backend.", BackendDiagnostics(), exception);
                FailBackend(writeFailure, id);
                throw writeFailure;
            }

            var completed = Task.WhenAny(completion.Task, Task.Delay(timeout)).GetAwaiter().GetResult();
            if (completed != completion.Task && !completion.Task.IsCompleted)
            {
                var timeoutFailure = new RpcException("Timeout", $"RPC method {method} exceeded {timeout} ms.", BackendDiagnostics());
                FailBackend(timeoutFailure, id);
            }

            var response = completion.Task.GetAwaiter().GetResult();
            if (response["error"] is JsonObject error)
            {
                var kind = ReadString(error, "type") ?? "PythonError";
                var message = ReadString(error, "message") ?? "The Python backend returned an error.";
                var trace = ReadString(error, "trace");
                throw new RpcException(kind, message, trace);
            }
            if (!response.ContainsKey("result"))
                throw new RpcException("InvalidResponse", "RPC response contains neither result nor error.");
            return response["result"]?.DeepClone();
        }
        finally
        {
            _pending.TryRemove(id, out _);
        }
    }

    /// <summary>Invokes a Python method when the result is not needed.</summary>
    /// <param name="method">The Python function or class-method name.</param>
    /// <param name="parameters">The JSON object containing named arguments.</param>
    /// <param name="timeoutMs">An optional per-call timeout in milliseconds.</param>
    public void Invoke(string method, JsonNode? parameters, int? timeoutMs = null)
    {
        _ = InvokeRaw(method, parameters, timeoutMs);
    }

    /// <summary>Invokes a Python method using a JSON string containing named arguments.</summary>
    /// <param name="method">The Python function or class-method name.</param>
    /// <param name="jsonArgs">A JSON object encoded as a string.</param>
    /// <param name="timeoutMs">An optional per-call timeout in milliseconds.</param>
    public void Invoke(string method, string jsonArgs, int? timeoutMs = null)
    {
        Invoke(method, Protocol.ParseArguments(jsonArgs), timeoutMs);
    }

    /// <summary>Invokes a Python method and converts its result to the requested type.</summary>
    /// <typeparam name="T">The expected result type.</typeparam>
    /// <param name="method">The Python function or class-method name.</param>
    /// <param name="parameters">The JSON object containing named arguments.</param>
    /// <param name="timeoutMs">An optional per-call timeout in milliseconds.</param>
    /// <param name="instanceId">An optional Python class instance ID.</param>
    /// <returns>The converted Python result.</returns>
    public T Invoke<T>(
        string method,
        JsonNode? parameters,
        int? timeoutMs = null,
        string? instanceId = null)
    {
        var result = InvokeRaw(method, parameters, timeoutMs, instanceId);
        if (result is null)
            throw new RpcException("InvalidResponse", $"RPC method {method} returned null, but {typeof(T).Name} was expected.");
        try
        {
            return result.Deserialize<T>()
                ?? throw new RpcException("InvalidResponse", $"RPC method {method} returned null, but {typeof(T).Name} was expected.");
        }
        catch (JsonException exception)
        {
            throw new RpcException("InvalidResponse", $"Unable to decode the result of {method} as {typeof(T).Name}.", innerException: exception);
        }
    }

    /// <summary>Invokes a Python method using JSON arguments and converts its result.</summary>
    /// <typeparam name="T">The expected result type.</typeparam>
    /// <param name="method">The Python function or class-method name.</param>
    /// <param name="jsonArgs">A JSON object encoded as a string.</param>
    /// <param name="timeoutMs">An optional per-call timeout in milliseconds.</param>
    /// <param name="instanceId">An optional Python class instance ID.</param>
    /// <returns>The converted Python result.</returns>
    public T Invoke<T>(
        string method,
        string jsonArgs,
        int? timeoutMs = null,
        string? instanceId = null)
    {
        return Invoke<T>(method, Protocol.ParseArguments(jsonArgs), timeoutMs, instanceId);
    }

    /// <summary>Invokes a Python class method on a specified class instance.</summary>
    public T InvokeInstance<T>(string method, string instanceId, JsonNode? parameters, int? timeoutMs = null) =>
        Invoke<T>(method, parameters, timeoutMs, instanceId);

    /// <summary>Invokes a Python class method on a specified class instance using JSON arguments.</summary>
    public T InvokeInstance<T>(string method, string instanceId, string jsonArgs, int? timeoutMs = null) =>
        Invoke<T>(method, jsonArgs, timeoutMs, instanceId);

    /// <summary>Invokes a Python class method on a specified class instance when no result is needed.</summary>
    public void InvokeInstance(string method, string instanceId, JsonNode? parameters, int? timeoutMs = null) =>
        _ = InvokeRaw(method, parameters, timeoutMs, instanceId);

    /// <summary>Invokes a Python class method on a specified class instance using JSON arguments.</summary>
    public void InvokeInstance(string method, string instanceId, string jsonArgs, int? timeoutMs = null) =>
        _ = InvokeRaw(method, Protocol.ParseArguments(jsonArgs), timeoutMs, instanceId);

    /// <summary>Stops the backend process and fails outstanding calls.</summary>
    public void Stop()
    {
        lock (_lifecycleLock)
        {
            if (_disposed)
                return;
            Process? process;
            lock (_writeLock)
            {
                process = _process;
                _running = false;
                _process = null;
                _stdin = null;
                _reader = null;
            }

            var stopped = new RpcException("BackendCrashed", "The Python backend was stopped.");
            FailPending(stopped);
            if (process is not null)
                RetireProcess(process);
        }
    }

    /// <summary>Stops the backend and releases client resources.</summary>
    public void Dispose()
    {
        lock (_lifecycleLock)
        {
            if (_disposed)
                return;
            Stop();
            _disposed = true;
        }
    }

    private void ReadLoop(Process process, Stream stdout)
    {
        Exception? failure = null;
        try
        {
            while (true)
            {
                var response = Protocol.ReadFrame(stdout);
                if (response is null)
                    break;
                if (response["id"]?.GetValue<long>() is not long id)
                    throw new InvalidDataException("RPC response has no numeric id.");
                if (!_pending.TryRemove(id, out var completion))
                    throw new InvalidDataException($"RPC response has an unknown id: {id}.");
                completion.TrySetResult(response);
            }
        }
        catch (Exception exception) when (exception is IOException or InvalidOperationException or JsonException or ObjectDisposedException or FormatException)
        {
            failure = exception;
        }

        lock (_lifecycleLock)
        {
            var shouldRetire = false;
            lock (_writeLock)
            {
                if (ReferenceEquals(process, _process) && _running)
                {
                    _running = false;
                    _process = null;
                    _stdin = null;
                    _reader = null;
                    shouldRetire = true;
                }
            }
            if (!shouldRetire)
                return;

            var message = failure is null
                ? "The Python backend closed its output stream."
                : $"The Python backend reader failed: {failure.Message}";
            RecordCrash();
            try
            {
                RetireProcess(process);
            }
            catch (Exception cleanupError)
            {
                message += $" Backend cleanup failed: {cleanupError.Message}";
                failure = new AggregateException(failure ?? new IOException(message), cleanupError);
            }
            FailPending(new RpcException("BackendCrashed", message, BackendDiagnostics(), failure));
        }
    }

    private void FailBackend(RpcException primaryFailure, long primaryId)
    {
        lock (_lifecycleLock)
        {
            Process? process;
            var wasRunning = false;
            lock (_writeLock)
            {
                wasRunning = _running;
                _running = false;
                process = _process;
                _stdin = null;
            }
            if (wasRunning)
                RecordCrash();
            Exception? cleanupFailure = null;
            if (process is not null)
            {
                try
                {
                    RetireProcess(process);
                }
                catch (Exception exception)
                {
                    cleanupFailure = exception;
                }
                lock (_writeLock)
                {
                    if (ReferenceEquals(process, _process))
                    {
                        _process = null;
                        _reader = null;
                    }
                }
            }

            foreach (var entry in _pending.ToArray())
            {
                if (_pending.TryRemove(entry.Key, out var completion))
                {
                    var failure = entry.Key == primaryId
                        ? primaryFailure
                        : new RpcException("BackendCrashed", "Another RPC request caused the backend to stop.", BackendDiagnostics());
                    if (cleanupFailure is not null)
                        failure = new RpcException(
                            failure.ErrorType,
                            failure.Message,
                            failure.Trace,
                            new AggregateException(failure, cleanupFailure));
                    completion.TrySetException(failure);
                }
            }
        }
    }

    private static void RetireProcess(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                try
                {
#if NET8_0_OR_GREATER
                    process.Kill(entireProcessTree: true);
#else
                    using (var treeKiller = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = Path.Combine(
                                Environment.GetFolderPath(Environment.SpecialFolder.System),
                                "taskkill.exe"),
                            Arguments = $"/PID {process.Id} /T /F",
                            UseShellExecute = false,
                            CreateNoWindow = true,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true
                        }
                    })
                    {
                        if (!treeKiller.Start())
                            throw new InvalidOperationException("Failed to start taskkill.exe.");
                        var standardOutput = treeKiller.StandardOutput.ReadToEndAsync();
                        var standardError = treeKiller.StandardError.ReadToEndAsync();
                        treeKiller.WaitForExit();
                        Task.WaitAll(standardOutput, standardError);
                        if (treeKiller.ExitCode != 0 && !process.HasExited)
                        {
                            throw new InvalidOperationException(
                                $"Failed to stop backend process tree: {standardOutput.Result}{standardError.Result}");
                        }
                    }
#endif
                }
                catch (InvalidOperationException) when (process.HasExited)
                {
                }
                process.WaitForExit();
            }
        }
        finally
        {
            process.Dispose();
        }
    }

    private void FailPending(RpcException failure)
    {
        foreach (var entry in _pending.ToArray())
        {
            if (_pending.TryRemove(entry.Key, out var completion))
                completion.TrySetException(failure);
        }
    }

    private static string? ReadString(JsonObject value, string key)
    {
        try
        {
            return value[key]?.GetValue<string>();
        }
        catch (InvalidOperationException)
        {
            throw new RpcException("InvalidResponse", $"RPC error field {key} must be a string.");
        }
    }

    private void AppendStderr(string line)
    {
        lock (_breakerLock)
        {
            var text = _stderrTail + line + Environment.NewLine;
            _stderrTail = text.Length <= 8192 ? text : text.Substring(text.Length - 8192);
        }
    }

    private string? BackendDiagnostics()
    {
        lock (_breakerLock)
            return string.IsNullOrWhiteSpace(_stderrTail) ? null : _stderrTail;
    }

    private void RecordCrash()
    {
        lock (_breakerLock)
        {
            var now = DateTime.UtcNow;
            TrimCrashes(now);
            _crashes.Enqueue(now);
        }
    }

    private bool IsBreakerOpen()
    {
        lock (_breakerLock)
        {
            TrimCrashes(DateTime.UtcNow);
            return _crashes.Count >= _breakerThreshold;
        }
    }

    private void TrimCrashes(DateTime now)
    {
        while (_crashes.Count > 0 && now - _crashes.Peek() > _breakerWindow)
            _crashes.Dequeue();
    }

    private static string QuoteArgument(string argument)
    {
        if (argument.Length == 0)
            return "\"\"";
        if (!argument.Any(character => char.IsWhiteSpace(character) || character == '"'))
            return argument;

        var quoted = new StringBuilder(argument.Length + 2);
        quoted.Append('"');
        var backslashes = 0;
        foreach (var character in argument)
        {
            if (character == '\\')
            {
                backslashes++;
                continue;
            }

            if (character == '"')
            {
                quoted.Append('\\', backslashes * 2 + 1);
                quoted.Append('"');
            }
            else
            {
                quoted.Append('\\', backslashes);
                quoted.Append(character);
            }
            backslashes = 0;
        }

        quoted.Append('\\', backslashes * 2);
        quoted.Append('"');
        return quoted.ToString();
    }
}
