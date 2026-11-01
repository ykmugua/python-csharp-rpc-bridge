# Local Zig compiler

The `modules/build.bat` one-click build uses Nuitka's Zig compiler mode. Put the
Windows x86_64 Zig distribution in a directory under `toolchain/` whose name
starts with `zig-`, for example:

```text
toolchain/zig-x86_64-windows-0.17.0/zig.exe
```

The batch file finds the `zig.exe`, adds its directory to `PATH` for that
build, and invokes Nuitka with `--zig`. Keep exactly one `toolchain/zig-*`
directory to avoid ambiguity. Zig toolchain files are ignored by Git and are
not included in source control.
