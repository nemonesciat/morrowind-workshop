// Shared by the launcher and the installer.
using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;

static class Common
{
    public const string Name = "Morrowind Workshop";
    public const string ExeName = "Morrowind Workshop.exe";
    public const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\MorrowindWorkshop";
    // Names for "is it running?", "please quit" (the installer, so files can be replaced) and
    // "show your window" (starting it again). One set per install folder, so copies in different
    // folders don't get in each other's way.
    public static string Tag(string root)
    {
        using (var sha = System.Security.Cryptography.SHA1.Create())
        {
            var h = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(Path.GetFullPath(root).TrimEnd('\\').ToLowerInvariant()));
            return BitConverter.ToString(h, 0, 6).Replace("-", "");
        }
    }
    public static string QuitEventName(string root) { return "MorrowindWorkshop.QuitRequest." + Tag(root); }
    public static string MutexName(string root) { return "MorrowindWorkshop.Launcher." + Tag(root); }
    public static string ShowEventName(string root) { return "MorrowindWorkshop.ShowRequest." + Tag(root); }
    // what version 1.0 used (one for the whole computer), so updating from it still closes it
    const string LegacyQuitEvent = "MorrowindWorkshop.QuitRequest", LegacyMutex = "MorrowindWorkshop.Launcher";

    // Allow paths over 260 characters ("\\?\" paths). Call first thing in Main.
    public static void EnableLongPaths()
    {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
    }

    public static string Long(string p)
    {
        if (p.StartsWith(@"\\?\")) return p;
        return @"\\?\" + Path.GetFullPath(p);
    }

    public static void DeleteTree(string dir)
    {
        string d = Long(dir);
        if (Directory.Exists(d)) Directory.Delete(d, true);
    }

    public static string DefaultFolder()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", Name);
    }

    public static string RunningFile(string root) { return Path.Combine(root, "workshop_running.json"); }

    // The address of a Workshop that is running from this folder, or null.
    public static string RunningUrl(string root)
    {
        try
        {
            string text = File.ReadAllText(RunningFile(root));
            Match m = Regex.Match(text, "\"url\"\\s*:\\s*\"([^\"]+)\"");
            if (!m.Success) return null;
            string url = m.Groups[1].Value;
            var req = (HttpWebRequest)WebRequest.Create(url + "api/link");
            req.Timeout = 2000;
            req.Proxy = null;
            using (var resp = (HttpWebResponse)req.GetResponse())
                return resp.StatusCode == HttpStatusCode.OK ? url : null;
        }
        catch { return null; }
    }

    // Ask a running Workshop to save and stop. True when it has stopped.
    public static bool AskToQuit(string root, int waitMs)
    {
        string url = RunningUrl(root);
        if (url == null) return true;
        try
        {
            var req = (HttpWebRequest)WebRequest.Create(url + "api/quit");
            req.Method = "POST";
            req.Timeout = 3000;
            req.Proxy = null;
            req.ContentLength = 0;
            req.Headers.Add("X-Workshop-Quit", "1");
            using (req.GetResponse()) { }
        }
        catch { }
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < waitMs)
        {
            Thread.Sleep(250);
            if (RunningUrl(root) == null) return true;
        }
        return false;
    }

    public static void OpenUrl(string url)
    {
        try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch { }
    }

    // A Windows shortcut (.lnk), through the shell's documented shortcut interface (IShellLink).
    public static void Shortcut(string lnk, string target, string workDir, string description)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(lnk));
        var link = (IShellLinkW)new ShellLink();
        link.SetPath(target);
        link.SetWorkingDirectory(workDir);
        link.SetIconLocation(target, 0);
        link.SetDescription(description);
        ((IPersistFile)link).Save(lnk, true);
    }

    public static string ShortcutTarget(string lnk)
    {
        try
        {
            var link = (IShellLinkW)new ShellLink();
            ((IPersistFile)link).Load(lnk, 0);
            var sb = new StringBuilder(1024);
            link.GetPath(sb, sb.Capacity, IntPtr.Zero, 0);
            return sb.ToString();
        }
        catch { return ""; }
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class ShellLink { }

    [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
    interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int cch, IntPtr findData, int flags);
        void GetIDList(out IntPtr idl);
        void SetIDList(IntPtr idl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int cch);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int cch);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int cch);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int showCmd);
        void SetShowCmd(int showCmd);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int cch, out int icon);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int icon);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, int reserved);
        void Resolve(IntPtr hwnd, int flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
    }

    public static string StartMenuLink()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), Name + ".lnk");
    }

    public static string DesktopLink()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), Name + ".lnk");
    }

    // Tell the launcher running from this folder to quit (it stops the Workshop cleanly first).
    public static void SignalLauncherQuit(string root, int waitMs)
    {
        Signal(QuitEventName(root), MutexName(root), waitMs);
        // a 1.0 launcher, if that's what is installed here
        string exe = Path.Combine(root, ExeName);
        bool legacyHere = false;
        try
        {
            foreach (var p in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(ExeName)))
                try { if (string.Equals(p.MainModule.FileName, exe, StringComparison.OrdinalIgnoreCase)) legacyHere = true; } catch { }
        }
        catch { }
        if (legacyHere) Signal(LegacyQuitEvent, LegacyMutex, waitMs);
    }

    static void Signal(string eventName, string mutexName, int waitMs)
    {
        try
        {
            EventWaitHandle ev;
            if (!EventWaitHandle.TryOpenExisting(eventName, out ev)) return;
            ev.Set();
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < waitMs)
            {
                Mutex m;
                if (!Mutex.TryOpenExisting(mutexName, out m)) return;
                m.Dispose();
                Thread.Sleep(250);
            }
        }
        catch { }
    }
}
