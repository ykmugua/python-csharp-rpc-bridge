using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace ModulePlatform.PyfRpc;

internal static class Protocol
{
    internal const int MaxFrame = 64 * 1024 * 1024;

    internal static byte[] EncodeFrame(long id, string method, JsonNode? parameters, string? instanceId = null)
    {
        var request = new JsonObject
        {
            ["id"] = id,
            ["method"] = method,
            ["params"] = parameters?.DeepClone() ?? new JsonObject()
        };
        if (instanceId is not null)
            request["instance_id"] = instanceId;
        var payload = JsonSerializer.SerializeToUtf8Bytes(request);
        if (payload.Length == 0 || payload.Length > MaxFrame)
            throw new RpcException("WriteFailed", $"RPC frame exceeds the {MaxFrame}-byte limit.");

        var frame = new byte[sizeof(uint) + payload.Length];
        var length = (uint)payload.Length;
        frame[0] = (byte)length;
        frame[1] = (byte)(length >> 8);
        frame[2] = (byte)(length >> 16);
        frame[3] = (byte)(length >> 24);
        Buffer.BlockCopy(payload, 0, frame, sizeof(uint), payload.Length);
        return frame;
    }

    internal static JsonObject ParseArguments(string json)
    {
        try
        {
            return JsonNode.Parse(json) as JsonObject
                ?? throw new RpcException("InvalidArguments", "jsonArgs must contain a JSON object.");
        }
        catch (JsonException exception)
        {
            throw new RpcException("InvalidArguments", "jsonArgs is not valid JSON.", innerException: exception);
        }
    }

    internal static JsonObject? ReadFrame(Stream stream)
    {
        var header = new byte[sizeof(uint)];
        if (!ReadExact(stream, header, 0, header.Length))
            return null;

        var length = (uint)(header[0] | header[1] << 8 | header[2] << 16 | header[3] << 24);
        if (length == 0 || length > MaxFrame)
            throw new InvalidDataException($"Invalid RPC frame length: {length}.");

        var payload = new byte[(int)length];
        if (!ReadExact(stream, payload, 0, payload.Length))
            throw new EndOfStreamException("The backend closed the stream in the middle of an RPC frame.");

        try
        {
            return JsonNode.Parse(payload) as JsonObject
                ?? throw new InvalidDataException("RPC response must be a JSON object.");
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException("The backend returned invalid JSON.", exception);
        }
    }

    private static bool ReadExact(Stream stream, byte[] buffer, int offset, int count)
    {
        var readTotal = 0;
        while (readTotal < count)
        {
            var read = stream.Read(buffer, offset + readTotal, count - readTotal);
            if (read == 0)
            {
                if (readTotal == 0)
                    return false;
                throw new EndOfStreamException("The backend closed the stream in the middle of an RPC frame.");
            }
            readTotal += read;
        }
        return true;
    }
}
