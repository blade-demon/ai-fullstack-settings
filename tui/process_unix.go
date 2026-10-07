//go:build darwin || linux

package main

import (
	"os/exec"
	"syscall"
)

func configureProcessGroup(cmd *exec.Cmd)               { cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} }
func signalProcessGroup(pid int, signal syscall.Signal) { _ = syscall.Kill(-pid, signal) }
func processGroupAlive(pid int) bool                    { return syscall.Kill(-pid, 0) != syscall.ESRCH }
