// Morrowind Workshop Setup.exe: installs the Workshop for the current Windows user
// (no administrator rights needed). The files travel inside this program as payload.zip.
// Installing again over an existing copy updates it and keeps projects and settings.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class SetupMain
{
    [STAThread]
    static int Main(string[] args)
    {
        Common.EnableLongPaths();
        // "/extract <folder>": just unpack the files there (a portable copy: no shortcuts, not listed in Windows)
        if (args.Length >= 2 && args[0].Equals("/extract", StringComparison.OrdinalIgnoreCase))
        {
            try { SetupForm.Extract(Path.GetFullPath(args[1]), null); return 0; }
            catch (Exception ex) { Console.Error.WriteLine(ex.Message); return 1; }
        }
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new SetupForm());
        return 0;
    }
}

class SetupForm : Form
{
    static readonly Color Bg = Color.FromArgb(30, 26, 21), Panel2 = Color.FromArgb(42, 37, 29),
        Gold = Color.FromArgb(226, 176, 74), Text1 = Color.FromArgb(222, 212, 189), Muted = Color.FromArgb(160, 148, 124);

    readonly TextBox folder = new TextBox(), oldFolder = new TextBox();
    readonly CheckBox desktop = new CheckBox(), bring = new CheckBox(), startNow = new CheckBox();
    readonly Button install = new Button(), cancel = new Button(), browse = new Button(), browseOld = new Button();
    readonly ProgressBar bar = new ProgressBar();
    readonly Label status = new Label(), title = new Label(), intro = new Label();
    readonly Panel options = new Panel(), progress = new Panel(), done = new Panel();
    readonly string existing;
    bool finished;

    public SetupForm()
    {
        Text = Common.Name + " " + BuildInfo.Version + " setup";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Font;
        Font = new Font("Segoe UI", 9.5f);
        ClientSize = new Size(560, 556);
        BackColor = Bg;
        ForeColor = Text1;

        existing = InstalledFolder();
        title.Text = existing != null ? "Update Morrowind Workshop" : "Install Morrowind Workshop";
        title.Font = new Font("Georgia", 17f, FontStyle.Bold);
        title.ForeColor = Gold;
        title.SetBounds(24, 18, 512, 36);
        intro.Text = existing != null
            ? "Morrowind Workshop is already installed. This puts version " + BuildInfo.Version + " in its place. Your projects and settings are kept."
            : "A modern, easy editor for making Morrowind mods with OpenMW. Build and furnish places, add people, " +
              "items, dialogue and quests, and try them in the running game straight away.";
        intro.ForeColor = Text1;
        intro.SetBounds(26, 58, 508, 46);
        // what you need, said before anything is installed
        var needs = new Label
        {
            Text = "What you need\n" +
                   "•  Windows 10 or 11 (64-bit)\n" +
                   "•  OpenMW 0.49 or newer (free, openmw.org), set up once with its Launcher\n" +
                   "•  Morrowind itself (for example from Steam or GOG)\n\n" +
                   "Everything else comes with the Workshop: no Python or other downloads, no administrator rights. " +
                   "The AI assistant is optional; it needs your own Anthropic API key and is paid per use.",
            ForeColor = Muted
        };
        needs.SetBounds(26, 108, 508, 142);
        Controls.AddRange(new Control[] { title, intro, needs });

        foreach (var p in new[] { options, progress, done })
        {
            p.SetBounds(0, 262, 560, 220);
            Controls.Add(p);
        }

        // ---- options
        var lf = Lbl("Install to", 26, 4);
        folder.SetBounds(26, 26, 420, 26);
        folder.Text = existing ?? Common.DefaultFolder();
        Style(folder);
        browse.Text = "Browse…";
        browse.SetBounds(454, 25, 80, 28);
        Style(browse);
        browse.Click += (s, e) => Pick(folder);
        desktop.Text = "Put a shortcut on the desktop";
        desktop.Checked = existing == null || File.Exists(Common.DesktopLink());
        desktop.SetBounds(26, 66, 500, 24);
        bring.Text = "Bring over projects and settings from an earlier Workshop folder:";
        bring.SetBounds(26, 100, 500, 24);
        oldFolder.SetBounds(46, 128, 400, 26);
        Style(oldFolder);
        browseOld.Text = "Browse…";
        browseOld.SetBounds(454, 127, 80, 28);
        Style(browseOld);
        browseOld.Click += (s, e) => { Pick(oldFolder); bring.Checked = oldFolder.Text.Length > 0; };
        string guess = GuessOldFolder();
        oldFolder.Text = guess ?? "";
        bring.Checked = guess != null && existing == null;
        bring.CheckedChanged += (s, e) => { oldFolder.Enabled = browseOld.Enabled = bring.Checked; };
        oldFolder.Enabled = browseOld.Enabled = bring.Checked;
        var oldNote = Lbl("(the folder with \"projects\" in it, such as one you unzipped before)", 46, 158);
        oldNote.ForeColor = Muted;
        options.Controls.AddRange(new Control[] { lf, folder, browse, desktop, bring, oldFolder, browseOld, oldNote });

        // ---- progress
        status.SetBounds(26, 30, 508, 44);
        bar.SetBounds(26, 80, 508, 22);
        progress.Controls.AddRange(new Control[] { status, bar });
        progress.Visible = false;

        // ---- done
        var dl = Lbl("", 26, 20);
        dl.Name = "doneText";
        dl.SetBounds(26, 20, 508, 90);
        startNow.Text = "Start Morrowind Workshop now";
        startNow.Checked = true;
        startNow.SetBounds(26, 116, 500, 24);
        done.Controls.AddRange(new Control[] { dl, startNow });
        done.Visible = false;

        install.Text = existing != null ? "Update" : "Install";
        install.SetBounds(350, 506, 92, 32);
        Style(install);
        install.BackColor = Color.FromArgb(90, 70, 32);
        install.Click += (s, e) => { if (finished) Finish(); else Start(); };
        cancel.Text = "Cancel";
        cancel.SetBounds(450, 506, 86, 32);
        Style(cancel);
        cancel.Click += (s, e) => Close();
        Controls.AddRange(new Control[] { install, cancel });
        AcceptButton = install;
    }

    Label Lbl(string text, int x, int y)
    {
        var l = new Label { Text = text, AutoSize = true };
        l.Location = new Point(x, y);
        return l;
    }

    void Style(Control c)
    {
        c.BackColor = Panel2;
        c.ForeColor = Text1;
        var b = c as Button;
        if (b != null) { b.FlatStyle = FlatStyle.Flat; b.FlatAppearance.BorderColor = Color.FromArgb(110, 90, 50); }
        var t = c as TextBox;
        if (t != null) t.BorderStyle = BorderStyle.FixedSingle;
    }

    void Pick(TextBox box)
    {
        using (var d = new FolderBrowserDialog())
        {
            if (Directory.Exists(box.Text)) d.SelectedPath = box.Text;
            if (d.ShowDialog(this) == DialogResult.OK) box.Text = d.SelectedPath;
        }
    }

    static string InstalledFolder()
    {
        try
        {
            using (var k = Registry.CurrentUser.OpenSubKey(Common.UninstallKey))
            {
                var loc = k == null ? null : k.GetValue("InstallLocation") as string;
                return loc != null && File.Exists(Path.Combine(loc, Common.ExeName)) ? loc : null;
            }
        }
        catch { return null; }
    }

    static bool LongPathsOn()
    {
        try
        {
            using (var k = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\FileSystem"))
                return k != null && Convert.ToInt32(k.GetValue("LongPathsEnabled", 0)) == 1;
        }
        catch { return false; }
    }

    // a Workshop folder next to (or above) this setup program, e.g. an unzipped earlier copy
    static string GuessOldFolder()
    {
        string here = Path.GetDirectoryName(Application.ExecutablePath);
        foreach (var d in new[] { here, Path.GetDirectoryName(here), Path.GetDirectoryName(Path.GetDirectoryName(here ?? "") ?? "") })
        {
            if (string.IsNullOrEmpty(d)) continue;
            if (Directory.Exists(Path.Combine(d, "projects")) && File.Exists(Path.Combine(d, "app", "workshop.py")))
                return d;
        }
        return null;
    }

    void Start()
    {
        string target = folder.Text.Trim();
        if (target.Length < 4 || !Path.IsPathRooted(target))
        {
            MessageBox.Show(this, "Choose a full folder path to install to.", Text);
            return;
        }
        if (Path.GetFullPath(target).Length + 1 + BuildInfo.LongestPath > 259 && !LongPathsOn())
        {
            MessageBox.Show(this, "That folder's path is too long for some of the Workshop's files on this computer " +
                "(Windows limits paths to 260 characters). Choose a shorter folder, like the suggested one.", Text);
            return;
        }
        string from = bring.Checked ? oldFolder.Text.Trim() : null;
        if (from != null && !Directory.Exists(Path.Combine(from, "projects")))
        {
            MessageBox.Show(this, "There is no \"projects\" folder in\n" + from + "\n\nChoose the folder of the earlier Workshop (it has app and projects in it), or untick that option.", Text);
            return;
        }
        if (from != null && string.Equals(Path.GetFullPath(from).TrimEnd('\\'), Path.GetFullPath(target).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
            from = null;
        if (Directory.Exists(target) && Directory.EnumerateFileSystemEntries(target).Any() &&
            !File.Exists(Path.Combine(target, Common.ExeName)) && existing == null &&
            MessageBox.Show(this, target + " already has other files in it. Install there anyway?", Text,
                            MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
            return;
        options.Visible = false;
        progress.Visible = true;
        install.Enabled = cancel.Enabled = false;
        bool wantDesktop = desktop.Checked;
        var t = new Thread(() =>
        {
            string err = null;
            try { Work(target, from, wantDesktop); }
            catch (Exception ex) { err = ex.Message; }
            BeginInvoke((Action)(() => Done(target, err)));
        });
        t.IsBackground = true;
        t.Start();
    }

    void Say(string text, int pct)
    {
        BeginInvoke((Action)(() => { status.Text = text; if (pct >= 0) bar.Value = Math.Min(100, pct); }));
    }

    void Work(string target, string from, bool wantDesktop)
    {
        Say("Closing Morrowind Workshop if it is running…", 2);
        Common.SignalLauncherQuit(target, 12000);
        if (!Common.AskToQuit(target, 10000))
            throw new Exception("Morrowind Workshop is still running and could not be closed. Quit it (right-click its icon by the clock) and try again.");

        Extract(target, Say);

        if (from != null)
        {
            Say("Bringing over your projects and settings…", 90);
            foreach (var d in new[] { "projects", "prefabs", "releases" })
                CopyNewer(Path.Combine(from, d), Path.Combine(target, d));
            foreach (var f in new[] { "workshop_settings.json", "play_commands.txt" })
                CopyFileNewer(Path.Combine(from, f), Path.Combine(target, f));
        }

        Say("Making shortcuts…", 95);
        string exe = Path.Combine(target, Common.ExeName);
        Common.Shortcut(Common.StartMenuLink(), exe, target, "Make Morrowind mods for OpenMW");
        if (wantDesktop) Common.Shortcut(Common.DesktopLink(), exe, target, "Make Morrowind mods for OpenMW");
        else if (File.Exists(Common.DesktopLink()) && Common.ShortcutTarget(Common.DesktopLink()).StartsWith(target, StringComparison.OrdinalIgnoreCase))
            File.Delete(Common.DesktopLink());

        // listed in Windows' "Installed apps", which removes it with the launcher's /uninstall
        using (var k = Registry.CurrentUser.CreateSubKey(Common.UninstallKey))
        {
            k.SetValue("DisplayName", Common.Name);
            k.SetValue("DisplayVersion", BuildInfo.Version);
            k.SetValue("Publisher", Common.Name);
            k.SetValue("DisplayIcon", exe + ",0");
            k.SetValue("InstallLocation", target);
            k.SetValue("UninstallString", "\"" + exe + "\" /uninstall");
            k.SetValue("QuietUninstallString", "\"" + exe + "\" /uninstall /quiet");
            k.SetValue("NoModify", 1, RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            k.SetValue("EstimatedSize", (int)BuildInfo.SizeKB, RegistryValueKind.DWord);
        }
        // Windows keeps the icons of a program it has seen before: the shortcuts, the taskbar and the corner
        // kept the old small icons after an update (the user, when the icon changed in 2.4.17). Told the icons
        // changed, it reads them again
        try { SHChangeNotify(0x08000000, 0x0000, IntPtr.Zero, IntPtr.Zero); } catch { }
        Say("Done.", 100);
    }

    [System.Runtime.InteropServices.DllImport("shell32.dll")]
    static extern void SHChangeNotify(int eventId, int flags, IntPtr item1, IntPtr item2);

    // Which running programs live in the install folder (the Workshop itself, or something started with
    // its Python, like a test script): named in the error, since "is the Workshop still open?" was not it
    // when a script run with the Workshop's python.exe held the folder.
    static string Holding(string target)
    {
        var names = new System.Collections.Generic.List<string>();
        try
        {
            foreach (var pr in Process.GetProcesses())
            {
                string path = null;
                try { path = pr.MainModule.FileName; } catch { continue; }
                if (path != null && path.StartsWith(target, StringComparison.OrdinalIgnoreCase))
                {
                    string cmd = pr.ProcessName + " (pid " + pr.Id + ")";
                    try { if (!string.IsNullOrEmpty(pr.MainWindowTitle)) cmd += " \"" + pr.MainWindowTitle + "\""; } catch { }
                    names.Add(cmd);
                }
            }
        }
        catch { }
        if (names.Count == 0) return "Is the Workshop still open? Close it (and anything started with its Python) and try again.";
        return "Still running from that folder: " + string.Join(", ", names) + ". Close it and try again.";
    }

    // Replace the program files in target with the ones in this setup (projects etc. are left alone).
    public static void Extract(string target, Action<string, int> say)
    {
        if (say == null) say = (t, p) => { };
        Directory.CreateDirectory(Common.Long(target));
        say("Removing the old program files…", 5);
        foreach (var d in new[] { "python", "app" })
        {
            string p = Path.Combine(target, d);
            for (int i = 0; i < 10 && Directory.Exists(Common.Long(p)); i++)
            {
                try { Common.DeleteTree(p); }
                catch (IOException) { Thread.Sleep(500); }
                catch (UnauthorizedAccessException) { Thread.Sleep(500); }
            }
            if (Directory.Exists(Common.Long(p))) throw new Exception("Could not replace " + p + ". " + Holding(target));
        }

        using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
        using (var zip = new ZipArchive(s, ZipArchiveMode.Read))
        {
            int n = 0, total = zip.Entries.Count;
            string full = Path.GetFullPath(target).TrimEnd('\\') + "\\";
            foreach (var e in zip.Entries)
            {
                string dest = Path.GetFullPath(Path.Combine(target, e.FullName.Replace('/', '\\')));
                if (!dest.StartsWith(full, StringComparison.OrdinalIgnoreCase)) continue;
                if (e.FullName.EndsWith("/")) { Directory.CreateDirectory(Common.Long(dest)); continue; }
                Directory.CreateDirectory(Common.Long(Path.GetDirectoryName(dest)));
                for (int attempt = 0; ; attempt++)
                {
                    try { e.ExtractToFile(Common.Long(dest), true); break; }
                    catch (IOException) { if (attempt > 8) throw; Thread.Sleep(500); }
                }
                if (++n % 50 == 0) say("Copying files… " + n + " of " + total, 8 + n * 80 / total);
            }
        }
    }

    static void CopyNewer(string src, string dst)
    {
        if (!Directory.Exists(src)) return;
        Directory.CreateDirectory(dst);
        foreach (var f in Directory.GetFiles(src))
            CopyFileNewer(f, Path.Combine(dst, Path.GetFileName(f)));
        foreach (var d in Directory.GetDirectories(src))
            CopyNewer(d, Path.Combine(dst, Path.GetFileName(d)));
    }

    static void CopyFileNewer(string src, string dst)
    {
        if (!File.Exists(src)) return;
        if (File.Exists(dst) && File.GetLastWriteTimeUtc(dst) >= File.GetLastWriteTimeUtc(src)) return;
        File.Copy(src, dst, true);
    }

    void Done(string target, string err)
    {
        progress.Visible = false;
        cancel.Enabled = true;
        if (err != null)
        {
            options.Visible = true;
            install.Enabled = true;
            MessageBox.Show(this, "Setup could not finish:\n\n" + err, Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        finished = true;
        done.Visible = true;
        done.Controls["doneText"].Text = "Morrowind Workshop " + BuildInfo.Version + " is installed in\n" + target +
            "\n\nStart it from the Start menu" + (desktop.Checked ? " or the desktop" : "") +
            ". It opens in your web browser; its icon by the clock lets you reopen or quit it.";
        install.Text = "Finish";
        install.Enabled = true;
        cancel.Visible = false;
        Tag = target;
    }

    void Finish()
    {
        if (startNow.Checked)
        {
            try
            {
                string target = (string)Tag;
                Process.Start(new ProcessStartInfo(Path.Combine(target, Common.ExeName)) { WorkingDirectory = target, UseShellExecute = true });
            }
            catch (Exception ex) { MessageBox.Show(this, ex.Message, Text); }
        }
        Close();
    }
}
