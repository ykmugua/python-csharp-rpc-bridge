using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;

namespace ModulePlatform.PyfRpc;

/// <summary>Resolves the configured location of a Python RPC backend executable.</summary>
public static class BackendLocator
{
    /// <summary>Finds a backend file using the environment, assembly metadata, or DLL directory.</summary>
    /// <param name="exeName">The backend executable file name.</param>
    /// <returns>The absolute path to the backend executable.</returns>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static string Resolve(string exeName)
    {
        if (string.IsNullOrWhiteSpace(exeName))
            throw new ArgumentException("A backend executable name is required.", nameof(exeName));
        var callerAssembly = Assembly.GetCallingAssembly();
        var directory = ResolveDirectory(callerAssembly, Assembly.GetEntryAssembly());
        return ExistingBackend(Path.Combine(directory, exeName));
    }

    /// <summary>Creates a client for a packaged backend, or starts Python with the generated RPC script.</summary>
    /// <param name="exeName">The optional standalone backend executable file name.</param>
    /// <param name="serverScriptName">The generated Python RPC server script file name.</param>
    /// <returns>A client configured to launch the available backend.</returns>
    [MethodImpl(MethodImplOptions.NoInlining)]
    public static StdioRpcClient CreateClient(string exeName, string serverScriptName)
    {
        if (string.IsNullOrWhiteSpace(exeName))
            throw new ArgumentException("A backend executable name is required.", nameof(exeName));
        if (string.IsNullOrWhiteSpace(serverScriptName))
            throw new ArgumentException("A backend server script name is required.", nameof(serverScriptName));

        var callerAssembly = Assembly.GetCallingAssembly();
        var directory = ResolveDirectory(callerAssembly, Assembly.GetEntryAssembly());
        var executablePath = Path.Combine(directory, exeName);
        if (File.Exists(executablePath))
            return new StdioRpcClient(Path.GetFullPath(executablePath));

        var scriptPath = Path.Combine(directory, serverScriptName);
        if (!File.Exists(scriptPath))
        {
            throw new FileNotFoundException(
                $"Neither Python backend executable nor RPC script was found in {directory}. " +
                $"Expected {exeName} or {serverScriptName}.",
                scriptPath);
        }

        var pythonPath = Environment.GetEnvironmentVariable("PYF_PYTHON");
        if (string.IsNullOrWhiteSpace(pythonPath))
            pythonPath = "python";
        return new StdioRpcClient(pythonPath, arguments: new[] { Path.GetFullPath(scriptPath) });
    }

    private static string ResolveDirectory(Assembly callerAssembly, Assembly? entryAssembly)
    {
        var envDirectory = Environment.GetEnvironmentVariable("PYF_BACKEND_DIR");
        if (!string.IsNullOrWhiteSpace(envDirectory))
            return Path.GetFullPath(envDirectory);

        foreach (var assembly in new[] { callerAssembly, entryAssembly }.Where(a => a is not null))
        {
            var configuredDirectory = assembly!
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .FirstOrDefault(attribute => attribute.Key == "PyfBackendDir")
                ?.Value;
            if (!string.IsNullOrWhiteSpace(configuredDirectory))
                return Path.GetFullPath(configuredDirectory);
        }

        var assemblyDirectory = Path.GetDirectoryName(callerAssembly.Location);
        if (string.IsNullOrWhiteSpace(assemblyDirectory))
            throw new DirectoryNotFoundException("Unable to determine the generated DLL directory.");
        return assemblyDirectory;
    }

    private static string ExistingBackend(string path)
    {
        var fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath))
            throw new FileNotFoundException($"Python RPC backend was not found: {fullPath}", fullPath);
        return fullPath;
    }
}
