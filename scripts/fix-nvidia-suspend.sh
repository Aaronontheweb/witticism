#!/bin/bash
# Systemd sleep hook to fix nvidia_uvm after suspend/resume
# Install to: /usr/lib/systemd/system-sleep/fix-nvidia-suspend

case "$1" in
    pre)
        # Before suspend - nothing needed with our config
        ;;
    post)
        # After resume - reload nvidia_uvm module
        echo "$(date): Reloading nvidia_uvm module after resume" >> /var/log/nvidia-suspend-fix.log
        
        # Wait a moment for system to stabilize
        sleep 2
        
        # Check if nvidia_uvm is loaded
        if lsmod | grep -q nvidia_uvm; then
            # Try to remove and reload the module
            rmmod nvidia_uvm 2>> /var/log/nvidia-suspend-fix.log
            
            # Small delay
            sleep 1
            
            # Reload the module
            modprobe nvidia_uvm 2>> /var/log/nvidia-suspend-fix.log
            
            if [ $? -eq 0 ]; then
                echo "$(date): Successfully reloaded nvidia_uvm" >> /var/log/nvidia-suspend-fix.log
            else
                echo "$(date): Failed to reload nvidia_uvm" >> /var/log/nvidia-suspend-fix.log
            fi
        else
            # Module not loaded, just load it
            modprobe nvidia_uvm 2>> /var/log/nvidia-suspend-fix.log
            echo "$(date): Loaded nvidia_uvm (was not loaded)" >> /var/log/nvidia-suspend-fix.log
        fi
        ;;
esac