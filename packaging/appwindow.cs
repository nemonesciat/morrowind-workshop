// The Workshop's own window: Microsoft Edge (part of Windows 10 and 11) in "app mode", which
// has no tabs or address bar and a taskbar button of its own. It opens with your normal Edge
// profile on purpose: a separate Edge settings folder gets signed in to your Windows Microsoft
// account by Edge itself (and starts syncing), which the Workshop must never cause.
// The window is found by its title (an app window's title is just the page's: "Morrowind
// Workshop"), and only that window is ever closed, never Edge itself.
// Without Edge, the Workshop opens in your default web browser instead.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32;

static class AppWindow
{
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    delegate bool EnumProc(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);

    const string Title = "Morrowind Workshop";

    public static string FindEdge()
    {
        foreach (var hive in new[] { Registry.CurrentUser, Registry.LocalMachine })
        {
            try
            {
                using (var k = hive.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"))
                {
                    var p = k == null ? null : k.GetValue(null) as string;
                    if (!string.IsNullOrEmpty(p) && File.Exists(p)) return p;
                }
            }
            catch { }
        }
        foreach (var pf in new[] { Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                                   Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles) })
        {
            string p = Path.Combine(pf, "Microsoft", "Edge", "Application", "msedge.exe");
            if (File.Exists(p)) return p;
        }
        return null;
    }

    // Edge windows showing the Workshop (normal Edge windows are titled "... - Microsoft Edge"). A second
    // window opened from the Workshop (web/twowin.js) is titled "Morrowind Workshop: <place>": counted
    // only with seconds, so showing the Workshop fronts the main window and quitting closes them all.
    public static List<IntPtr> Windows(bool seconds = false)
    {
        var edge = new HashSet<uint>();
        try { foreach (var p in Process.GetProcessesByName("msedge")) edge.Add((uint)p.Id); } catch { }
        var found = new List<IntPtr>();
        if (edge.Count == 0) return found;
        EnumWindows((h, l) =>
        {
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            if (edge.Contains(pid) && IsWindowVisible(h))
            {
                var sb = new StringBuilder(256);
                GetWindowText(h, sb, sb.Capacity);
                string t = sb.ToString();
                if (t == Title || (seconds && t.StartsWith(Title + ": "))) found.Add(h);
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }

    // Show the Workshop: bring its window to the front, or open it. False when Edge isn't there
    // (the caller then uses the default browser).
    public static bool Show(string url)
    {
        foreach (var h in Windows())
        {
            if (IsIconic(h)) ShowWindow(h, 9);              // (restore if minimised)
            SetForegroundWindow(h);
            return true;
        }
        string edge = FindEdge();
        if (edge == null) return false;
        Process.Start(new ProcessStartInfo(edge, "--app=\"" + url + "\" --window-size=1440,900") { UseShellExecute = false });
        return true;
    }

    // Close the Workshop's window (quitting from the tray, or updating), the way its ✕ does.
    public static void Close()
    {
        foreach (var h in Windows(true)) PostMessage(h, 0x0112, (IntPtr)0xF060, IntPtr.Zero);   // WM_SYSCOMMAND, SC_CLOSE
    }
}
