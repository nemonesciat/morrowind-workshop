# Building the installer

The installer (`Morrowind Workshop Setup.exe`) is built on Windows from the files in this repository.
Nothing is downloaded during the build.

## You need

- Windows 10 or 11, 64-bit.
- **Python 3.13, 64-bit**, from [python.org](https://www.python.org/downloads/) (the release
  installer was built with Python 3.13.5). The build copies this Python into the installer, so the
  people who install the Workshop don't need Python.
- Anthropic's Python library, for the optional AI assistant. The release used version 1.14.0:

  ```
  py -3 -m pip install anthropic==1.14.0
  ```

- The C# compiler of the .NET Framework 4.8, which is part of Windows:
  `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`. Nothing to install.

## Build

From the folder this file is in:

```
py -3 packaging\build.py
```

It takes a minute or two and makes `packaging\out\Morrowind Workshop Setup.exe`, and the same files as a portable zip, `packaging\out\Morrowind Workshop <version> portable.zip`. Along the way it:

1. Copies `app/` and writes the version from `packaging/version.txt` into it.
2. Assembles a private Python for the installer: Python's own files and standard library (without
   tests, IDLE and tkinter), the `anthropic` library and its dependencies (found from their package
   metadata), and the DLLs these need (found by reading the programs' import tables). The libraries
   are precompiled to `.pyc` files.
3. Checks that this Python can import everything the Workshop uses, with nothing else on the PATH.
4. Writes `README.txt` (from `packaging/README.md`) and `THIRD_PARTY_NOTICES.txt`.
5. Compiles the launcher (with `packaging/app.manifest`: runs as the normal user), `Morrowind Workshop.exe` (`launcher.cs`, `appwindow.cs`, `common.cs`).
6. Zips all of it and compiles the installer, `Morrowind Workshop Setup.exe` (`setup.cs`,
   `common.cs`), with the zip inside it as a resource.

The installer installs per user into `%LOCALAPPDATA%\Programs\Morrowind Workshop`, without
administrator rights, and adds a Start menu shortcut and an entry in Windows' Installed apps.
`Morrowind Workshop Setup.exe /extract <folder>` only unpacks the files, which is handy for checking
what's inside.

Because the build bundles the Python of the computer it runs on, two builds are not byte-identical,
but they contain the same Workshop.
