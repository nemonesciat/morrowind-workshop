// Morrowind Workshop.exe: starts the Workshop (its own Python, no console window) and keeps
// an icon in the notification area to open it again, see its log, or quit.
// "Morrowind Workshop.exe /uninstall" removes it (Windows' "Installed apps" calls that).
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class Launcher
{
    // (a property, not a field: nothing may touch file paths before EnableLongPaths runs)
    public static string Root { get { return AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\'); } }

    [STAThread]
    static int Main(string[] args)
    {
        Common.EnableLongPaths();
        Application.EnableVisualStyles();
        if (args.Length > 0 && args[0].Equals("/uninstall", StringComparison.OrdinalIgnoreCase))
            return Uninstaller.Run(args.Contains("/quiet"));
        if (args.Length >= 3 && args[0].Equals("/uninstall-finish", StringComparison.OrdinalIgnoreCase))
        {
            int pid; int.TryParse(args[2], out pid);
            return Uninstaller.Finish(args[1], args.Contains("/keepdata"), args.Contains("/quiet"), pid);
        }
        bool first;
        using (var mutex = new Mutex(true, Common.MutexName(Root), out first))
        {
            if (!first)
            {
                // already running: ask it to bring its window to the front
                EventWaitHandle show;
                if (EventWaitHandle.TryOpenExisting(Common.ShowEventName(Root), out show)) show.Set();
                else { string url = Common.RunningUrl(Root); if (url != null) Common.OpenUrl(url); }
                return 0;
            }
            string running = Common.RunningUrl(Root);
            if (running != null) { Common.OpenUrl(running); return 0; }   // started some other way
            // the Workshop keeps projects and settings next to itself (the portable download can be anywhere)
            try { string probe = Path.Combine(Root, ".write-test"); File.WriteAllText(probe, ""); File.Delete(probe); }
            catch
            {
                MessageBox.Show("Morrowind Workshop can't save in this folder:\n" + Root + "\n\nMove the Morrowind Workshop folder " +
                    "somewhere you can save files, such as Documents or the desktop, and start it from there.",
                    Common.Name, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return 1;
            }
            if (!File.Exists(Path.Combine(Root, "python", "pythonw.exe")))
            {
                MessageBox.Show("Morrowind Workshop's files are missing (python folder). Please run the setup again.",
                                Common.Name, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            using (var tray = new Tray()) Application.Run(tray);
        }
        return 0;
    }
}

class Tray : ApplicationContext
{
    readonly NotifyIcon icon;
    readonly Process proc;
    readonly StreamWriter logw;
    readonly string logPath;
    readonly EventWaitHandle quitEvent;
    readonly SynchronizationContext ui;
    bool quitting;

    public Tray()
    {
        ui = new WindowsFormsSynchronizationContext();
        SynchronizationContext.SetSynchronizationContext(ui);
        string root = Launcher.Root;
        logPath = Path.Combine(root, "workshop.log");
        try { if (File.Exists(logPath)) File.Copy(logPath, Path.Combine(root, "workshop.previous.log"), true); } catch { }
        logw = new StreamWriter(new FileStream(logPath, FileMode.Create, FileAccess.Write, FileShare.ReadWrite), new UTF8Encoding(false));
        logw.AutoFlush = true;
        logw.WriteLine("Morrowind Workshop " + BuildInfo.Version + " started " + DateTime.Now);

        icon = new NotifyIcon();
        icon.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        icon.Text = "Morrowind Workshop";
        var menu = new ContextMenuStrip();
        var open = menu.Items.Add("Open Morrowind Workshop", null, (s, e) => OpenWorkshop());
        open.Font = new Font(open.Font, FontStyle.Bold);
        menu.Items.Add("Open in my web browser", null, (s, e) =>
        {
            string url = Common.RunningUrl(Launcher.Root);
            if (url != null) Common.OpenUrl(url);
        });
        menu.Items.Add("Show log", null, (s, e) => ShowLog());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Quit", null, (s, e) => Quit());
        icon.ContextMenuStrip = menu;
        icon.DoubleClick += (s, e) => OpenWorkshop();
        icon.Visible = true;

        // pythonw: the windowless Python, made for programs like this one
        var psi = new ProcessStartInfo(Path.Combine(root, "python", "pythonw.exe"),
                                       "-X utf8 \"" + Path.Combine(root, "app", "workshop.py") + "\"");
        psi.WorkingDirectory = root;
        psi.UseShellExecute = false;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["WORKSHOP_NO_BROWSER"] = "1";       // (we open its own window instead)
        psi.EnvironmentVariables["PYTHONHASHSEED"] = "0";            // (sets in one order every run: the same furnish)
        psi.EnvironmentVariables.Remove("PYTHONHOME");
        psi.EnvironmentVariables.Remove("PYTHONPATH");
        proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
        proc.OutputDataReceived += (s, e) => Log(e.Data);
        proc.ErrorDataReceived += (s, e) => Log(e.Data);
        proc.Exited += (s, e) => ui.Post(_ => OnExited(), null);
        try
        {
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
        }
        catch (Exception ex)
        {
            MessageBox.Show("Morrowind Workshop could not start:\n" + ex.Message, Common.Name, MessageBoxButtons.OK, MessageBoxIcon.Error);
            ExitThread();
            return;
        }
        // the installer (when updating) asks us to quit through this
        quitEvent = new EventWaitHandle(false, EventResetMode.AutoReset, Common.QuitEventName(Launcher.Root));
        var t = new Thread(() => { quitEvent.WaitOne(); ui.Post(_ => Quit(), null); }) { IsBackground = true };
        t.Start();
        // starting the Workshop again brings its window to the front through this
        showEvent = new EventWaitHandle(false, EventResetMode.AutoReset, Common.ShowEventName(Launcher.Root));
        new Thread(() => { while (true) { showEvent.WaitOne(); ui.Post(_ => OpenWorkshop(), null); } }) { IsBackground = true }.Start();

        // open the window as soon as the Workshop answers, then quit when that window is closed
        new Thread(() =>
        {
            var sw = Stopwatch.StartNew();
            while (!quitting && Common.RunningUrl(Launcher.Root) == null && sw.ElapsedMilliseconds < 120000) Thread.Sleep(400);
            if (quitting) return;
            ui.Post(_ => OpenWorkshop(), null);
            bool seen = false;
            int gone = 0;
            while (!quitting)
            {
                Thread.Sleep(1500);
                if (inBrowser) return;                   // (no Edge: a browser tab we can't watch)
                bool showing = AppWindow.Windows(true).Count > 0;      // (a second window keeps it running too)
                if (showing) { seen = true; gone = 0; }
                else if (seen && ++gone >= 2) { ui.Post(_ => Quit(), null); return; }
            }
        }) { IsBackground = true }.Start();
    }

    readonly EventWaitHandle showEvent;
    volatile bool inBrowser;

    void Log(string line)
    {
        if (line == null) return;
        lock (logw) { try { logw.WriteLine(line); } catch { } }
    }

    void OpenWorkshop()
    {
        string url = Common.RunningUrl(Launcher.Root);
        if (url == null) { icon.ShowBalloonTip(4000, "Morrowind Workshop", "Still starting up, one moment…", ToolTipIcon.Info); return; }
        bool ok = false;
        try { ok = AppWindow.Show(url); } catch { }
        if (!ok)
        {
            inBrowser = true;
            Common.OpenUrl(url);
            icon.ShowBalloonTip(6000, "Morrowind Workshop", "It's open in your web browser. Right-click this icon to quit.", ToolTipIcon.Info);
        }
    }

    void ShowLog()
    {
        try { Process.Start(new ProcessStartInfo("notepad.exe", "\"" + logPath + "\"")); } catch { }
    }

    void Quit()
    {
        if (quitting) return;
        quitting = true;
        icon.Text = "Morrowind Workshop: closing…";
        new Thread(() =>
        {
            try { AppWindow.Close(); } catch { }
            Common.AskToQuit(Launcher.Root, 8000);
            try { if (!proc.HasExited && !proc.WaitForExit(4000)) proc.Kill(); } catch { }
            ui.Post(_ => ExitThread(), null);
        }) { IsBackground = true }.Start();
    }

    void OnExited()
    {
        if (!quitting)
        {
            string tail = "";
            try
            {
                lock (logw) { }
                var lines = File.ReadAllLines(logPath, Encoding.UTF8);
                tail = string.Join("\n", lines.Skip(Math.Max(0, lines.Length - 12)));
            }
            catch { }
            var r = MessageBox.Show("Morrowind Workshop stopped unexpectedly.\n\n" + tail + "\n\nOpen the full log?",
                                    Common.Name, MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (r == DialogResult.Yes) ShowLog();
        }
        ExitThread();
    }

    protected override void ExitThreadCore()
    {
        icon.Visible = false;
        base.ExitThreadCore();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            icon.Dispose();
            try { logw.Dispose(); } catch { }
        }
        base.Dispose(disposing);
    }
}

static class Uninstaller
{
    // Step 1, from the installed program: ask, then hand over to a copy of this program in the
    // temporary folder (a running program can't remove its own file), like standard uninstallers do.
    public static int Run(bool quiet)
    {
        string root = Launcher.Root;
        if (!quiet && MessageBox.Show("Remove Morrowind Workshop from this computer?\n\n" +
                "Mods you made stay in your OpenMW data folder either way.",
                Common.Name, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            return 1;
        bool keepData = true;
        if (!quiet && Directory.Exists(Path.Combine(root, "projects")))
            keepData = MessageBox.Show("Keep your Workshop projects and settings?\n\n" +
                "Yes: they stay in " + root + " and are there again if you reinstall.\n" +
                "No: delete them too.", Common.Name, MessageBoxButtons.YesNo, MessageBoxIcon.Question,
                MessageBoxDefaultButton.Button1) == DialogResult.Yes;

        Common.SignalLauncherQuit(root, 10000);
        Common.AskToQuit(root, 8000);
        try
        {
            string tmp = Path.Combine(Path.GetTempPath(), "Morrowind Workshop uninstall");
            Directory.CreateDirectory(tmp);
            string helper = Path.Combine(tmp, "Morrowind Workshop Uninstall.exe");
            File.Copy(Application.ExecutablePath, helper, true);
            string args = "/uninstall-finish \"" + root + "\" " + Process.GetCurrentProcess().Id +
                          (keepData ? " /keepdata" : "") + (quiet ? " /quiet" : "");
            Process.Start(new ProcessStartInfo(helper, args) { UseShellExecute = false, WorkingDirectory = tmp });
            return 0;
        }
        catch
        {
            return Finish(root, keepData, quiet, 0);          // (no temporary folder: do it from here)
        }
    }

    // Step 2, from the temporary copy: once the installed program has closed, remove everything.
    public static int Finish(string root, bool keepData, bool quiet, int waitFor)
    {
        if (waitFor > 0)
            try { Process.GetProcessById(waitFor).WaitForExit(15000); } catch { }
        bool fromCopy = !string.Equals(Path.GetFullPath(Path.GetDirectoryName(Application.ExecutablePath)).TrimEnd('\\'),
                                       Path.GetFullPath(root).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase);
        var gone = new[] { "python", "app", "cache", "browser", "link_data" }.ToList();
        var files = new[] { "workshop.log", "workshop.previous.log", "workshop_running.json", "README.txt",
                            "THIRD_PARTY_NOTICES.txt" }.ToList();
        if (fromCopy) files.Add(Common.ExeName);
        if (!keepData)
        {
            gone.AddRange(new[] { "projects", "prefabs", "releases", "backups", "reports" });
            files.AddRange(new[] { "workshop_settings.json", "play_commands.txt" });
        }
        foreach (var d in gone)
            try { Common.DeleteTree(Path.Combine(root, d)); } catch { }
        foreach (var f in files)
            try { File.Delete(Path.Combine(root, f)); } catch { }
        foreach (var lnk in new[] { Common.StartMenuLink(), Common.DesktopLink() })
        {
            try
            {
                // only our own shortcut (pointing into this folder)
                if (File.Exists(lnk) && Common.ShortcutTarget(lnk).StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    File.Delete(lnk);
            }
            catch { }
        }
        try { Registry.CurrentUser.DeleteSubKeyTree(Common.UninstallKey, false); } catch { }

        // the folder itself, when nothing is left in it (kept projects stay, and so does the folder)
        try { if (!Directory.EnumerateFileSystemEntries(root).Any()) Directory.Delete(root); } catch { }
        if (!quiet)
            MessageBox.Show("Morrowind Workshop has been removed." + (keepData ? "\nYour projects are still in " + root + "." : ""),
                            Common.Name, MessageBoxButtons.OK, MessageBoxIcon.Information);
        return 0;
    }
}
