package main

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const (
	configFile   = ".redteam-cli-config.json"
	toolDBFile   = "tool_db.json"
	logDirectory = "redteam_logs"
)

type Tool struct {
	Name      string   `json:"name"`
	Command   string   `json:"command"`
	Args      string   `json:"args"`
	Install   string   `json:"install"`
	Paths     []string `json:"paths"`
	Installed bool     `json:"-"`
	Path      string   `json:"-"`
}

type Scenario struct {
	Name     string   `json:"name"`
	Phases   []Phase  `json:"phases"`
	Prechecks []string `json:"prechecks"`
}

type Phase struct {
	Tool string `json:"tool"`
	Args string `json:"args"`
}

type Config struct {
	Scenarios []Scenario `json:"scenarios"`
	Tools     []Tool     `json:"tools"`
}

var (
	config     Config
	configLock sync.Mutex
	target     string
	module     string
)

func init() {
	flag.StringVar(&target, "target", "", "Target host/IP for operations")
	flag.StringVar(&module, "module", "", "Metasploit module name")
}

func main() {
	loadConfig()
	loadToolDB()
	scanSystemTools()

	flag.Parse()

	if len(os.Args) < 2 {
		printHelp()
		return
	}

	switch os.Args[1] {
	case "list":
		listCommand()
	case "scenario":
		scenarioCommand()
	case "tool":
		toolCommand()
	default:
		printHelp()
	}
}

func listCommand() {
	if len(os.Args) < 3 {
		listScenarios()
		listTools()
		return
	}

	switch os.Args[2] {
	case "scenarios":
		listScenarios()
	case "tools":
		listTools()
	default:
		printHelp()
	}
}

func scenarioCommand() {
	if len(os.Args) < 3 {
		printHelp()
		return
	}

	switch os.Args[2] {
	case "run":
		if len(os.Args) < 4 {
			log.Fatal("Missing scenario name")
		}
		runScenario(os.Args[3])
	default:
		printHelp()
	}
}

func toolCommand() {
	if len(os.Args) < 3 {
		printHelp()
		return
	}

	switch os.Args[2] {
	case "run":
		if len(os.Args) < 4 {
			log.Fatal("Missing tool name")
		}
		runTool(os.Args[3])
	default:
		printHelp()
	}
}

func loadConfig() {
	configPath := filepath.Join(os.Getenv("HOME"), configFile)
	data, err := os.ReadFile(configPath)
	if err != nil {
		initializeDefaultConfig()
		return
	}

	if err := json.Unmarshal(data, &config); err != nil {
		log.Fatalf("Error loading config: %v", err)
	}
}

func initializeDefaultConfig() {
	config = Config{
		Scenarios: []Scenario{},
		Tools:     []Tool{},
	}
	saveConfig()
}

func saveConfig() {
	data, err := json.MarshalIndent(config, "", "  ")
	if err != nil {
		log.Fatalf("Error saving config: %v", err)
	}

	configPath := filepath.Join(os.Getenv("HOME"), configFile)
	if err := os.WriteFile(configPath, data, 0600); err != nil {
		log.Fatalf("Error writing config: %v", err)
	}
}

func loadToolDB() {
	data, err := os.ReadFile(toolDBFile)
	if err != nil {
		log.Fatalf("Error loading tool DB: %v", err)
	}

	if err := json.Unmarshal(data, &config.Tools); err != nil {
		log.Fatalf("Error parsing tool DB: %v", err)
	}
}

func scanSystemTools() {
	for i, tool := range config.Tools {
		config.Tools[i].Installed = false
		for _, path := range tool.Paths {
			if _, err := exec.LookPath(path); err == nil {
				config.Tools[i].Installed = true
				config.Tools[i].Path = path
				break
			}
		}
	}
}

func listScenarios() {
	fmt.Println("\nAvailable Scenarios:")
	for _, scenario := range config.Scenarios {
		fmt.Printf("  %s (%d phases)\n", scenario.Name, len(scenario.Phases))
	}
}

func listTools() {
	fmt.Println("\nAvailable Tools:")
	for _, tool := range config.Tools {
		status := "✗"
		if tool.Installed {
			status = "✓"
		}
		fmt.Printf("  %-15s %s\n", tool.Name, status)
	}
}

func runScenario(name string) {
	var scenario *Scenario
	for _, s := range config.Scenarios {
		if s.Name == name {
			scenario = &s
			break
		}
	}

	if scenario == nil {
		log.Fatalf("Scenario %s not found", name)
	}

	fmt.Printf("\nRunning scenario: %s\n", scenario.Name)
	for i, phase := range scenario.Phases {
		fmt.Printf("\n=== Phase %d/%d ===\n", i+1, len(scenario.Phases))
		executePhase(phase)
	}
	fmt.Println("\nScenario complete!")
}

func executePhase(phase Phase) {
	tool := getTool(phase.Tool)
	if tool == nil {
		log.Printf("Tool %s not found", phase.Tool)
		return
	}

	if !tool.Installed {
		log.Printf("Tool %s not installed! Visit %s", tool.Name, tool.Install)
		return
	}

	args := replaceVariables(phase.Args)
	cmd := exec.Command(tool.Path, strings.Fields(args)...)

	logFile := createLogFile(tool.Name)
	defer logFile.Close()

	var wg sync.WaitGroup
	wg.Add(2)

	stdout, _ := cmd.StdoutPipe()
	stderr, _ := cmd.StderrPipe()

	go streamOutput(stdout, logFile, &wg)
	go streamOutput(stderr, logFile, &wg)

	if err := cmd.Start(); err != nil {
		log.Printf("Error starting command: %v", err)
		return
	}

	if err := cmd.Wait(); err != nil {
		log.Printf("Command failed: %v", err)
	}
	wg.Wait()
}

func runTool(name string) {
	tool := getTool(name)
	if tool == nil {
		log.Fatalf("Tool %s not found", name)
	}

	if !tool.Installed {
		log.Fatalf("Tool %s not installed! Visit %s", tool.Name, tool.Install)
	}

	args := replaceVariables(tool.Args)
	cmd := exec.Command(tool.Path, strings.Fields(args)...)

	logFile := createLogFile(tool.Name)
	defer logFile.Close()

	var wg sync.WaitGroup
	wg.Add(2)

	stdout, _ := cmd.StdoutPipe()
	stderr, _ := cmd.StderrPipe()

	go streamOutput(stdout, logFile, &wg)
	go streamOutput(stderr, logFile, &wg)

	if err := cmd.Start(); err != nil {
		log.Fatalf("Error starting command: %v", err)
	}

	if err := cmd.Wait(); err != nil {
		log.Printf("Command failed: %v", err)
	}
	wg.Wait()
}

func getTool(name string) *Tool {
	for _, t := range config.Tools {
		if strings.EqualFold(t.Name, name) {
			return &t
		}
	}
	return nil
}

func replaceVariables(input string) string {
	replacer := strings.NewReplacer(
		"{target}", target,
		"{module}", module,
	)
	return replacer.Replace(input)
}

func createLogFile(context string) *os.File {
	os.Mkdir(logDirectory, 0755)
	timestamp := time.Now().Format("20060102_150405")
	filename := fmt.Sprintf("%s_%s.log", context, timestamp)
	file, err := os.Create(filepath.Join(logDirectory, filename))
	if err != nil {
		log.Printf("Error creating log file: %v", err)
		return nil
	}
	return file
}

func streamOutput(pipe io.ReadCloser, logFile *os.File, wg *sync.WaitGroup) {
	defer wg.Done()
	scanner := bufio.NewScanner(pipe)
	for scanner.Scan() {
		line := scanner.Text()
		fmt.Println(line)
		if logFile != nil {
			logFile.WriteString(line + "\n")
		}
	}
}

func printHelp() {
	fmt.Println(`Red Team CLI Orchestrator

Usage:
  rtcli [command]

Commands:
  list               List available scenarios and tools
  scenario run [name]  Run a scenario
  tool run [name]      Run a single tool

Flags:
  -target string    Target host/IP for operations
  -module string    Metasploit module name

Examples:
  rtcli list
  rtcli scenario run penetration-test -target 192.168.1.1
  rtcli tool run nmap -target 10.0.0.5`)
}
