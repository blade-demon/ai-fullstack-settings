//go:build darwin || linux

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// The test subprocess uses the real CLI and signal handlers, isolated from the
// test runner so a regression cannot terminate the test runner itself.
func TestUISignalCLIHelper(t *testing.T) {
	if os.Getenv("TEAM_TUI_SIGNAL_HELPER") != "1" {
		return
	}
	page := os.Getenv("TEAM_TUI_SIGNAL_PAGE")
	if page == "" {
		page = "home"
	}
	os.Exit(runCLI([]string{"--support-dir", os.Getenv("TEAM_TUI_SIGNAL_SUPPORT"), "--page", page}, os.Stdin, os.Stdout, os.Stderr))
}

func TestUITerminationSignalsCancelAndReapTask(t *testing.T) {
	python, err := exec.LookPath("python3")
	if err != nil {
		t.Skip("python3 is required to allocate the controlling PTY")
	}
	for _, scenario := range []string{"hangup", "terminate", "interrupt", "interactive-terminate", "interactive-ctrlc", "terminate-backpressure"} {
		t.Run(scenario, func(t *testing.T) {
			support := t.TempDir()
			fixtureScript(t, support, "scripts/check-env.sh", "echo $$ > job.pid\ntrap 'exit 0' INT TERM\nwhile :; do sleep 0.05; done")
			page := "home"
			if strings.HasPrefix(scenario, "interactive-") {
				page = "cleanup"
				fixtureScript(t, support, "scripts/run-cleanup.sh", "exec python3 -u backend.py")
				if err := os.WriteFile(filepath.Join(support, "backend.py"), []byte(interactiveSignalBackend), 0600); err != nil {
					t.Fatal(err)
				}
			}
			cmd := exec.Command(python, "-c", signalPTYProbe, os.Args[0], support, scenario)
			cmd.Env = append(os.Environ(), "TEAM_TUI_SIGNAL_HELPER=1", "TEAM_TUI_SIGNAL_SUPPORT="+support, "TEAM_TUI_SIGNAL_PAGE="+page, "HOME="+support, "TERM=xterm-256color")
			output, err := cmd.CombinedOutput()
			if err != nil {
				t.Fatalf("signal lifecycle failed: %v\n%s", err, output)
			}
			if _, err := os.Stat(filepath.Join(support, "job.pid")); err != nil {
				t.Fatal("fixture task did not start")
			}
		})
	}
}

const signalPTYProbe = `
import errno, fcntl, os, pathlib, pty, select, signal, struct, subprocess, sys, termios, time
binary, support, scenario = sys.argv[1:]
master, slave = pty.openpty()
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
# A separate open avoids changing the child's own descriptor flags.
blocker = os.open(os.ttyname(slave), os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK) if scenario == 'terminate-backpressure' else None
def controlling_terminal():
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
stderr_path = pathlib.Path(support) / 'signal-stderr.log'
stderr_file = stderr_path.open('wb')
proc = subprocess.Popen([binary, '-test.run=^TestUISignalCLIHelper$'], stdin=slave, stdout=slave, stderr=stderr_file, preexec_fn=controlling_terminal)
os.close(slave)
jobpid = None
childpid = None
output = b''
def pump_terminal(delay=.05):
    global output
    if master is None:
        time.sleep(delay)
        return
    if select.select([master], [], [], delay)[0]:
        try:
            chunk = os.read(master, 65536)
        except OSError as error:
            if error.errno != errno.EIO:
                raise
            return
        output = (output + chunk)[-262144:]
def read_until(text):
    global output
    deadline = time.monotonic() + 10
    while text.encode() not in output and time.monotonic() < deadline:
        pump_terminal()
    assert text.encode() in output, f'missing {text}: {output[-1000:]!r}'
try:
    if scenario.startswith('interactive-'):
        read_until('安全卸载')
        output = b''
        os.write(master, b'\x1b[B\r')
        read_until('确认操作')
        output = b''
        os.write(master, b'\r')
        read_until('INTERACTIVE_READY')
        childpid = int((pathlib.Path(support) / 'child.pid').read_text())
    marker = pathlib.Path(support) / 'job.pid'
    deadline = time.monotonic() + 10
    while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
        pump_terminal(.02)
    assert marker.exists(), 'background fixture did not start'
    jobpid = int(marker.read_text().strip())
    if blocker is not None:
        # Deliberately fill the PTY output queue. This is a separate regression
        # for prompt task cancellation when a terminal stops consuming output.
        for _ in range(1024):
            try:
                os.write(blocker, b'X' * 65536)
            except BlockingIOError:
                break
        else:
            raise AssertionError('could not create PTY output backpressure')
        time.sleep(.1)
    if scenario == 'hangup':
        os.close(master)
        master = None
        expected = 129
    elif scenario == 'interactive-ctrlc':
        output = b''
        os.write(master, b'\x03')
        read_until('已取消')
        assert proc.poll() is None, 'Ctrl-C during ExecProcess should return to the result page'
        os.write(master, b'q')
        expected = 130
    else:
        sig = signal.SIGTERM if scenario in ('terminate', 'interactive-terminate', 'terminate-backpressure') else signal.SIGINT
        os.kill(proc.pid, sig)
        expected = 128 + sig
    if blocker is not None:
        # Do not drain until the backend has stopped. Reaping must not depend
        # on Bubble Tea being able to finish writing its terminal output.
        stopped = False
        cancellation_deadline = time.monotonic() + 7
        while time.monotonic() < cancellation_deadline:
            try:
                os.kill(jobpid, 0)
            except ProcessLookupError:
                stopped = True
                break
            time.sleep(.02)
        assert stopped, 'backend survived 7s because terminal shutdown blocked cancellation'
    # A real terminal keeps consuming output. Stopping PTY reads here can
    # block Bubble Tea's renderer shutdown before runCLI reaches job cleanup.
    deadline = time.monotonic() + 12
    while proc.poll() is None and time.monotonic() < deadline:
        pump_terminal()
    if proc.poll() is None:
        # Diagnostics happen only after the unchanged acceptance deadline.
        # stderr is a file so SIGQUIT stacks are available even after SIGHUP.
        try:
            os.kill(proc.pid, signal.SIGQUIT)
        except ProcessLookupError:
            pass
        diagnostic_deadline = time.monotonic() + 3
        while proc.poll() is None and time.monotonic() < diagnostic_deadline:
            pump_terminal()
        raise AssertionError(f'{scenario}: 12s exit deadline exceeded; SIGQUIT stacks:\n' + stderr_path.read_text(errors='replace'))
    code = proc.wait()
    assert code == expected, f'{scenario}: expected exit {expected}, got {code}; stderr:\n' + stderr_path.read_text(errors='replace')
    for pid in (jobpid, childpid):
        if pid is None:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError(f'{scenario}: task {pid} survived UI exit')
    if scenario.startswith('interactive-'):
        assert (pathlib.Path(support) / 'interrupted').read_text() == 'child reaped', 'uninstaller did not receive a graceful interrupt'
finally:
    # Release PTY backpressure even on assertion failures before waiting for a
    # killed process; macOS can otherwise wait for the terminal during exit.
    if master is not None:
        os.close(master)
        master = None
    if blocker is not None:
        os.close(blocker)
        blocker = None
    if proc.poll() is None:
        proc.kill()
    for pgid in (proc.pid, jobpid):
        if pgid is None:
            continue
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for pid in (jobpid, childpid):
        if pid is None:
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait(timeout=5)
    stderr_file.close()
`

// Simulate an uninstaller/bootloader which owns a child and forwards SIGINT.
const interactiveSignalBackend = `
import os, pathlib, signal, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
def interrupt(signum, frame):
    child.send_signal(signal.SIGINT)
    child.wait(timeout=3)
    pathlib.Path('interrupted').write_text('child reaped')
    sys.exit(130)
signal.signal(signal.SIGINT, interrupt)
pathlib.Path('job.pid').write_text(str(os.getpid()))
pathlib.Path('child.pid').write_text(str(child.pid))
print('INTERACTIVE_READY', flush=True)
while True:
    time.sleep(.1)
`
