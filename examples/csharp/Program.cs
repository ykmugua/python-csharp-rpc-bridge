using System;
using System.Text.Json;
using System.Text.Json.Nodes;
using ModulePlatform;

SampleRuntime.Start();
try
{
    Console.WriteLine($"add(20, 22) = {SampleFunctions.Add_pyf(20, 22)}");
    int[] remaining = SampleFunctions.Delete_item_pyf(new[] { 10, 20, 30 }, 1);
    Console.WriteLine($"After delete: [{string.Join(", ", remaining)}]");

    double[] floats = SampleFunctions.Echo_floats_pyf(new[] { 1.25, -2.5, 3.0 });
    Console.WriteLine($"Double array: [{string.Join(", ", floats)}]");

    string[] strings = SampleFunctions.Echo_strings_pyf(new[] { "hello", "你好" });
    Console.WriteLine($"String array: [{string.Join(", ", strings)}]");

    bool[] flags = SampleFunctions.Echo_bools_pyf(new[] { true, false, true });
    Console.WriteLine($"Boolean array: [{string.Join(", ", flags)}]");

    JsonObject[] records = SampleFunctions.Echo_records_pyf(new[]
    {
        new JsonObject { ["id"] = 1, ["score"] = 95 },
        new JsonObject { ["id"] = 2, ["score"] = 88 }
    });
    Console.WriteLine($"JSON object array: {JsonSerializer.Serialize(records)}");

    using var french = TextProcessor.Create(lang: "fr", verbose: true);
    using var german = TextProcessor.Create(lang: "de", verbose: true);

    Console.WriteLine($"French: {french.Normalize_pyf("  hello   world  ")}");
    Console.WriteLine($"German: {german.Normalize_pyf("  hello   world  ")}");
    Console.WriteLine($"French language property: {french.Lang}");
    french.Lang = "fr-CA";
    french.Verbose = false;
    Console.WriteLine($"Updated language: {french.Lang}");
    Console.WriteLine($"Updated verbose: {french.Verbose}");
    Console.WriteLine($"French calls: {french.Calls}");
    french.Calls = 10;
    Console.WriteLine($"French calls after assignment: {french.Calls}");
    Console.WriteLine($"German calls: {german.Get_calls_pyf()}");
}
finally
{
    SampleRuntime.Stop();
}
