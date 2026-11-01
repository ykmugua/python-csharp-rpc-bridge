namespace ModulePlatform.PyfRpc;

/// <summary>Describes an RPC, protocol, or Python backend failure.</summary>
public sealed class RpcException : Exception
{
    /// <summary>Gets the backend or transport error category.</summary>
    public string ErrorType { get; }

    /// <summary>Gets the Python traceback, when one was returned by the backend.</summary>
    public string? Trace { get; }

    /// <summary>Initializes an RPC exception with its category and diagnostic details.</summary>
    /// <param name="errorType">The backend or transport error category.</param>
    /// <param name="message">A description of the failure.</param>
    /// <param name="trace">The optional Python traceback.</param>
    /// <param name="innerException">The optional underlying exception.</param>
    public RpcException(string errorType, string message, string? trace = null, Exception? innerException = null)
        : base(message, innerException)
    {
        ErrorType = errorType;
        Trace = trace;
    }
}
