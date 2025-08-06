#!/usr/bin/env python3
"""Check supervisor status and logs."""

import subprocess
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and return the result."""
    try:
        print(f"\n=== {description} ===")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        print(f"Return code: {result.returncode}")
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print(f"❌ Command timed out: {cmd}")
        return False
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_log_file(log_path, description, lines=20):
    """Check a log file."""
    try:
        print(f"\n=== {description} ===")
        
        if not Path(log_path).exists():
            print(f"❌ Log file does not exist: {log_path}")
            return False
        
        print(f"📄 Last {lines} lines of {log_path}:")
        result = subprocess.run(f"tail -{lines} {log_path}", shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        else:
            print("(Log file is empty)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading log file: {e}")
        return False

def check_processes():
    """Check running processes."""
    processes = [
        ("supervisord", "Supervisor daemon"),
        ("redis-server", "Redis server"),
        ("python3.*main.py", "Main application"),
        ("python3.*translation_worker", "Translation worker"),
        ("nginx", "Nginx web server")
    ]
    
    print("\n=== Process Check ===")
    
    for process_pattern, description in processes:
        try:
            result = subprocess.run(f"pgrep -f '{process_pattern}'", shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                print(f"✅ {description}: Running (PIDs: {', '.join(pids)})")
            else:
                print(f"❌ {description}: Not running")
                
        except Exception as e:
            print(f"❌ Error checking {description}: {e}")

def check_ports():
    """Check if required ports are listening."""
    ports = [
        (6379, "Redis"),
        (8000, "Application"),
        (80, "Nginx")
    ]
    
    print("\n=== Port Check ===")
    
    for port, service in ports:
        try:
            result = subprocess.run(f"netstat -tlnp | grep :{port}", shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout:
                print(f"✅ Port {port} ({service}): Listening")
                print(f"   {result.stdout.strip()}")
            else:
                print(f"❌ Port {port} ({service}): Not listening")
                
        except Exception as e:
            print(f"❌ Error checking port {port}: {e}")

def main():
    print("🔍 Supervisor and Service Status Check")
    print("=" * 50)
    
    # Check supervisor status
    run_command("supervisorctl status", "Supervisor Status")
    
    # Check processes
    check_processes()
    
    # Check ports
    check_ports()
    
    # Check log files
    log_files = [
        ("/var/log/supervisor/supervisord.log", "Supervisor Main Log"),
        ("/var/log/supervisor/redis.log", "Redis Log"),
        ("/var/log/supervisor/app.log", "Application Log"),
        ("/var/log/supervisor/worker.log", "Worker Log"),
        ("/var/log/supervisor/nginx.log", "Nginx Log")
    ]
    
    for log_path, description in log_files:
        check_log_file(log_path, description)
    
    # Additional Redis checks
    run_command("redis-cli ping", "Redis Ping Test")
    run_command("redis-cli info server", "Redis Server Info")
    
    print("\n" + "=" * 50)
    print("🔍 Check complete!")

if __name__ == "__main__":
    main()
