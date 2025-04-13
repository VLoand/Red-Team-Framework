import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext
import subprocess
import shutil
import os
import json
import re
from threading import Thread, Lock
from datetime import datetime

# Configuration constants
CONFIG_FILE = os.path.expanduser("~/.redteam_gui_config.json")
TOOL_DB_FILE = os.path.join(os.path.dirname(__file__), "tool_db.json")
LOG_DIR = os.path.join(os.path.expanduser("~"), "redteam_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Dark theme colors
COLOR_SCHEME = {
    "bg": "#2e2e2e",
    "fg": "#ffffff",
    "secondary_bg": "#3e3e3e",
    "accent": "#ff4d4d",
    "success": "#00ff00",
    "warning": "#ff9900",
    "error": "#ff0000"
}

class RedTeamGUI:
    def __init__(self, root):
        self.root = root
        self.running_processes = {}
        self.process_lock = Lock()
        self.current_scenario = None
        self.tool_db = self.load_tool_db()
        self.config = self.load_config()
        self.scan_system_tools()
        
        self.setup_gui()
        self.setup_menu()
        self.check_initial_setup()
        self.refresh_scenarios()

    def scan_system_tools(self):
        """Automatically detect installed tools"""
        tool_paths = {
            'nmap': ['nmap', '/usr/bin/nmap', 'C:\\Program Files\\Nmap\\nmap.exe'],
            'msfconsole': ['msfconsole', '/opt/metasploit-framework/bin/msfconsole']
        }
        
        for tool in self.tool_db['tools']:
            tool_name = tool['command'].lower()
            found_path = None
            for path in tool_paths.get(tool_name, [tool['command']]):
                if shutil.which(path):
                    found_path = path
                    break
            tool['installed'] = found_path is not None
            tool['path'] = found_path or tool['command']

    def setup_gui(self):
        self.root.title("Red Team Orchestrator v2.0")
        self.root.geometry("1280x720")
        self.root.minsize(1024, 600)
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configure colors and styles
        self.root.configure(bg=COLOR_SCHEME["bg"])
        self.style.configure(".", background=COLOR_SCHEME["bg"], foreground=COLOR_SCHEME["fg"])
        self.style.configure("TNotebook", background=COLOR_SCHEME["bg"])
        self.style.configure("TNotebook.Tab", 
                           background=COLOR_SCHEME["secondary_bg"], 
                           foreground=COLOR_SCHEME["fg"], 
                           padding=[15,5])
        self.style.map("TNotebook.Tab", background=[("selected", COLOR_SCHEME["accent"])])
        self.style.configure('Installed.TButton', foreground='green')
        self.style.configure('Missing.TButton', foreground='red')
        
        # Main notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Scenario Runner Tab
        self.scenario_frame = ttk.Frame(self.notebook)
        self.setup_scenario_runner()
        self.notebook.add(self.scenario_frame, text="Scenario Runner")
        
        # Quick Access Tools Tab
        self.tools_frame = ttk.Frame(self.notebook)
        self.setup_quick_tools()
        self.notebook.add(self.tools_frame, text="Quick Access Tools")
        
        # Status Bar
        self.status_bar = ttk.Label(self.root, text="Ready", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_scenario_runner(self):
        # Scenario selection panel
        left_panel = ttk.Frame(self.scenario_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        
        ttk.Label(left_panel, text="Available Scenarios:", font=("Helvetica", 12, "bold")).pack(pady=5)
        self.scenario_listbox = tk.Listbox(left_panel, width=35, height=15, 
                                         bg=COLOR_SCHEME["secondary_bg"],
                                         fg=COLOR_SCHEME["fg"], 
                                         selectbackground=COLOR_SCHEME["accent"])
        self.scenario_listbox.pack(pady=5)
        
        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="New Scenario", command=self.create_scenario).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Edit Scenario", command=self.edit_scenario).pack(side=tk.LEFT, padx=2)
        
        # Execution panel
        right_panel = ttk.Frame(self.scenario_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.console = scrolledtext.ScrolledText(right_panel, wrap=tk.WORD, 
                                               bg=COLOR_SCHEME["secondary_bg"],
                                               fg=COLOR_SCHEME["fg"], 
                                               insertbackground=COLOR_SCHEME["fg"])
        self.console.tag_config('session', foreground='green')
        self.console.tag_config('port', foreground='yellow')
        self.console.tag_config('error', foreground='red')
        self.console.pack(fill=tk.BOTH, expand=True)
        
        control_frame = ttk.Frame(right_panel)
        control_frame.pack(fill=tk.X, pady=10)
        ttk.Button(control_frame, text="Start Scenario", command=self.start_scenario).pack(side=tk.LEFT, padx=5)
        self.progress = ttk.Progressbar(control_frame, mode='determinate')
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)

    def setup_quick_tools(self):
        categories = ["Reconnaissance", "Initial Access", "Execution", "Evasion"]
        for cat in categories:
            frame = ttk.LabelFrame(self.tools_frame, text=cat)
            frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
            
            tools = [t for t in self.tool_db["tools"] if t["category"] == cat]
            for tool in tools:
                btn = ttk.Button(
                    frame, 
                    text=f"{tool['name']} {'✓' if tool['installed'] else '✗'}",
                    style='Installed.TButton' if tool['installed'] else 'Missing.TButton',
                    command=lambda t=tool: self.execute_tool(t),
                    width=20
                )
                btn.pack(pady=2)

    def load_tool_db(self):
        default_tools = {
            "tools": [
                {
                    "name": "Nmap",
                    "category": "Reconnaissance",
                    "command": "nmap",
                    "args": "-sV -T4 {target}",
                    "install": "https://nmap.org/download.html"
                },
                {
                    "name": "Metasploit",
                    "category": "Exploitation",
                    "command": "msfconsole",
                    "args": "-q -x 'use exploit/{module}; set RHOSTS {target}; run'",
                    "install": "https://github.com/rapid7/metasploit-framework"
                },
            ]
        }
        
        try:
            if os.path.exists(TOOL_DB_FILE):
                with open(TOOL_DB_FILE, 'r') as f:
                    return json.load(f)
            with open(TOOL_DB_FILE, 'w') as f:
                json.dump(default_tools, f, indent=4)
            return default_tools
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load tool database: {str(e)}")
            return default_tools

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE) as f:
                    return json.load(f)
            return {"theme": "dark", "auto_update": True, "scenarios": []}
        except Exception as e:
            messagebox.showerror("Error", f"Config load failed: {str(e)}")
            return {"scenarios": []}

    def refresh_scenarios(self):
        self.scenario_listbox.delete(0, tk.END)
        for scenario in self.config.get("scenarios", []):
            self.scenario_listbox.insert(tk.END, scenario["name"])

    def create_scenario(self):
        name = simpledialog.askstring("New Scenario", "Enter scenario name:")
        if name:
            scenario = {
                "name": name,
                "phases": [],
                "prechecks": []
            }
            self.config["scenarios"].append(scenario)
            self.edit_scenario(scenario)
            self.refresh_scenarios()
            self.save_config()

    def edit_scenario(self, scenario=None):
        if not scenario:
            sel = self.scenario_listbox.curselection()
            if not sel:
                messagebox.showinfo("Info", "Select a scenario to edit first!")
                return
            scenario = self.config["scenarios"][sel[0]]
            
        edit_win = tk.Toplevel(self.root)
        edit_win.title(f"Editing {scenario['name']}")
        
        # Phase configuration
        ttk.Label(edit_win, text="Phases:").pack(pady=5)
        phase_list = tk.Listbox(edit_win, width=50, height=10)
        phase_list.pack(fill=tk.X, padx=10)
        
        for phase in scenario["phases"]:
            phase_list.insert(tk.END, f"{phase['tool']}: {phase.get('args', '')}")
        
        # Tool selection
        ttk.Label(edit_win, text="Available Tools:").pack(pady=5)
        tool_combobox = ttk.Combobox(edit_win, 
                                    values=[t['name'] for t in self.tool_db['tools']])
        tool_combobox.pack(fill=tk.X, padx=10)
        
        # Argument input
        ttk.Label(edit_win, text="Arguments:").pack(pady=5)
        arg_entry = ttk.Entry(edit_win)
        arg_entry.pack(fill=tk.X, padx=10)
        
        def add_phase():
            tool_name = tool_combobox.get()
            if not tool_name:
                return
            tool = next(t for t in self.tool_db['tools'] if t['name'] == tool_name)
            scenario['phases'].append({
                'tool': tool_name,
                'command': tool['command'],
                'args': arg_entry.get()
            })
            phase_list.insert(tk.END, f"{tool_name}: {arg_entry.get() or 'No args'}")
            arg_entry.delete(0, tk.END)
            self.save_config()
            
        ttk.Button(edit_win, text="Add Phase", command=add_phase).pack(pady=10)
        edit_win.transient(self.root)
        edit_win.grab_set()

    def start_scenario(self):
        selection = self.scenario_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "No scenario selected")
            return
            
        scenario = self.config["scenarios"][selection[0]]
        
        # Pre-execution checks
        missing_tools = []
        for phase in scenario["phases"]:
            tool = next((t for t in self.tool_db["tools"] if t["name"] == phase["tool"]), None)
            if not tool or not tool.get('installed', False):
                missing_tools.append(phase["tool"])
        
        if missing_tools:
            messagebox.showwarning("Missing Tools", 
                                f"Required tools missing:\n{', '.join(missing_tools)}")
            return
            
        self.current_scenario = {
            'name': scenario['name'],
            'phases': scenario['phases'],
            'current_phase': 0,
            'total_phases': len(scenario['phases'])
        }
        self.progress['value'] = 0
        self.execute_scenario_phase()

    def execute_scenario_phase(self):
        if not self.current_scenario:
            return
            
        phase = self.current_scenario['phases'][self.current_scenario['current_phase']]
        tool = next(t for t in self.tool_db["tools"] if t["name"] == phase["tool"])
        
        cmd = f"{tool['path']} {phase.get('args', '')}"
        self.console.insert(tk.END, 
                          f"\n=== Phase {self.current_scenario['current_phase']+1}/{self.current_scenario['total_phases']} ===\n"
                          f"Executing: {cmd}\n")
        Thread(target=self.run_scenario_command, args=(cmd,), daemon=True).start()

    def run_scenario_command(self, command):
        try:
            process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT
            )
            
            while True:
                output = process.stdout.readline()
                if not output and process.poll() is not None:
                    break
                
                decoded = output.decode(errors='replace')
                self.parse_output(decoded)
                self.root.after(0, self.update_console, decoded)
                
            self.root.after(0, self.handle_scenario_progress)
            
        except Exception as e:
            self.root.after(0, self.log_error, str(e))

    def parse_output(self, line):
        if 'open' in line and 'port' in line:
            port = re.findall(r'(\d+)/tcp', line)
            if port:
                self.root.after(0, self.highlight_port, port[0])
        if 'Session' in line and 'opened' in line:
            session_id = re.findall(r'Session (\d+) opened', line)
            if session_id:
                self.root.after(0, self.highlight_session, session_id[0])

    def update_console(self, text):
        self.console.insert(tk.END, text)
        self.console.see(tk.END)

    def highlight_port(self, port):
        self.console.insert(tk.END, f"\n[!] Open port detected: {port}\n", "port")

    def highlight_session(self, session_id):
        self.console.insert(tk.END, f"\n[!] New session opened: {session_id}\n", "session")

    def handle_scenario_progress(self):
        if self.current_scenario:
            self.current_scenario['current_phase'] += 1
            progress = (self.current_scenario['current_phase'] / 
                      self.current_scenario['total_phases']) * 100
            self.progress['value'] = progress
            
            if self.current_scenario['current_phase'] < self.current_scenario['total_phases']:
                self.execute_scenario_phase()
            else:
                messagebox.showinfo("Scenario Complete", 
                                  "All phases executed successfully!")
                self.current_scenario = None
                self.progress['value'] = 0

    def execute_tool(self, tool_config):
        try:
            cmd = f"{tool_config.get('path', tool_config['command'])} {tool_config.get('args', '')}"
            Thread(target=self.run_command, args=(cmd,), daemon=True).start()
        except Exception as e:
            self.log_error(f"Failed to execute {tool_config['name']}: {str(e)}")

    def run_command(self, command):
        try:
            process = subprocess.Popen(
                command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT
            )
            
            while True:
                output = process.stdout.readline()
                if not output and process.poll() is not None:
                    break
                self.root.after(0, self.update_console, output.decode())
                
        except Exception as e:
            self.root.after(0, self.log_error, str(e))

    def log_error(self, message):
        self.console.insert(tk.END, f"ERROR: {message}\n", "error")
        self.console.see(tk.END)

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config: {str(e)}")

    def setup_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)

    def check_initial_setup(self):
        if not os.path.exists(TOOL_DB_FILE):
            messagebox.showwarning("Setup Required", "Tool database not found. Creating default configuration.")

if __name__ == "__main__":
    root = tk.Tk()
    app = RedTeamGUI(root)
    root.mainloop()