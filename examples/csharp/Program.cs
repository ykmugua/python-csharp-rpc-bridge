using System;
using ModulePlatform;

SampleRuntime.Start();
try
{
    Console.WriteLine($"add(20, 22) = {SampleFunctions.Add_pyf(20, 22)}");

    using var french = TextProcessor.Create(lang: "fr", verbose: true);
    using var german = TextProcessor.Create(lang: "de", verbose: true);

    Console.WriteLine($"French: {french.Normalize_pyf("  hello   world  ")}");
    Console.WriteLine($"German: {german.Normalize_pyf("  hello   world  ")}");
    Console.WriteLine($"French calls: {french.Get_calls_pyf()}");
    Console.WriteLine($"German calls: {german.Get_calls_pyf()}");
}
finally
{
    SampleRuntime.Stop();
}
