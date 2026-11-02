# Check Virtualization Setup

You are helping the user check if the system is properly set up to run virtualized workloads and remediate any issues.

## Your tasks:

1. **Check if CPU supports virtualization:**

   **Intel (VT-x):**
   ```bash
   grep -E "vmx" /proc/cpuinfo
   ```

   **AMD (AMD-V):**
   ```bash
   grep -E "svm" /proc/cpuinfo
   ```

   If no output, virtualization is not supported or not enabled in BIOS.

2. **Check if virtualization is enabled in BIOS:**
   ```bash
   sudo apt install cpu-checker
   sudo kvm-ok
   ```

   If it says KVM can be used, virtualization is enabled.
   If not, user needs to enable it in BIOS/UEFI.

3. **Check current virtualization software:**

   **KVM/QEMU:**
   ```bash
   which qemu-system-x86_64
   lsmod | grep kvm
   ```

   **VirtualBox:**
   ```bash
   which virtualbox
   VBoxManage --version
   ```

   **VMware:**
   ```bash
   which vmware
   systemctl status vmware
   ```

   **Docker (containerization):**
   ```bash
   docker --version
   systemctl status docker
   ```

4. **Check KVM kernel modules:**
   ```bash
   lsmod | grep kvm
   ```

   Should show:
   - `kvm_intel` (for Intel)
   - `kvm_amd` (for AMD)
   - `kvm` (base module)

   If not loaded, try:
   ```bash
   sudo modprobe kvm
   sudo modprobe kvm_intel  # or kvm_amd
   ```

5. **Install KVM and related tools (if not installed):**
   ```bash
   sudo apt update
   sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager
   ```

6. **Check libvirt status:**
   ```bash
   sudo systemctl status libvirtd
   ```

   If not running:
   ```bash
   sudo systemctl enable libvirtd
   sudo systemctl start libvirtd
   ```

7. **Add user to required groups:**
   ```bash
   sudo usermod -aG libvirt $USER
   sudo usermod -aG kvm $USER
   ```

   User needs to log out and back in for group changes to take effect.

8. **Verify user permissions:**
   ```bash
   groups
   ```

   Should include: `libvirt` and `kvm`

9. **Check libvirt connectivity:**
   ```bash
   virsh list --all
   ```

   If permission denied, user is not in libvirt group or not logged back in.

10. **Check virtualization networking:**

    **Default network:**
    ```bash
    virsh net-list --all
    ```

    If default network is not active:
    ```bash
    virsh net-start default
    virsh net-autostart default
    ```

    **Bridge networking:**
    ```bash
    ip link show
    brctl show  # if bridge-utils installed
    ```

11. **Check nested virtualization (if needed):**

    **For Intel:**
    ```bash
    cat /sys/module/kvm_intel/parameters/nested
    ```

    **For AMD:**
    ```bash
    cat /sys/module/kvm_amd/parameters/nested
    ```

    If shows `N` or `0`, nested virtualization is disabled.

    To enable:
    ```bash
    echo "options kvm_intel nested=1" | sudo tee /etc/modprobe.d/kvm-intel.conf
    # or for AMD:
    echo "options kvm_amd nested=1" | sudo tee /etc/modprobe.d/kvm-amd.conf
    ```

    Then reload:
    ```bash
    sudo modprobe -r kvm_intel
    sudo modprobe kvm_intel
    ```

12. **Check IOMMU for PCIe passthrough (if needed):**
    ```bash
    dmesg | grep -i iommu
    ```

    If IOMMU is needed, add to kernel parameters in `/etc/default/grub`:
    ```
    GRUB_CMDLINE_LINUX_DEFAULT="quiet splash intel_iommu=on"
    # or for AMD:
    GRUB_CMDLINE_LINUX_DEFAULT="quiet splash amd_iommu=on"
    ```

    Then update grub:
    ```bash
    sudo update-grub
    sudo reboot
    ```

13. **Check available storage pools:**
    ```bash
    virsh pool-list --all
    ```

    Create default pool if needed:
    ```bash
    virsh pool-define-as default dir --target /var/lib/libvirt/images
    virsh pool-start default
    virsh pool-autostart default
    ```

14. **Check system resources for virtualization:**
    ```bash
    free -h
    df -h /var/lib/libvirt/images
    cat /proc/cpuinfo | grep "processor" | wc -l
    ```

    Recommendations:
    - At least 4GB RAM for light VMs
    - At least 20GB free disk space
    - Multiple CPU cores recommended

15. **Test VM creation (small test):**
    ```bash
    virt-install --name test-vm \
      --ram 512 \
      --disk size=1 \
      --cdrom /path/to/iso \
      --graphics vnc \
      --check all=off \
      --dry-run
    ```

16. **Check for conflicting virtualization:**
    VirtualBox and KVM can sometimes conflict. Check if both are installed:
    ```bash
    dpkg -l | grep -E "virtualbox|qemu-kvm"
    ```

    VirtualBox kernel modules can conflict with KVM:
    ```bash
    lsmod | grep vbox
    ```

17. **Check virtualization acceleration:**
    ```bash
    ls -l /dev/kvm
    ```

    Should be:
    ```
    crw-rw---- 1 root kvm /dev/kvm
    ```

18. **Install virt-manager (GUI) if desired:**
    ```bash
    sudo apt install virt-manager
    ```

    Test launch:
    ```bash
    virt-manager
    ```

19. **Check for Secure Boot issues:**
    Secure Boot can prevent some virtualization modules from loading:
    ```bash
    mokutil --sb-state
    ```

    If Secure Boot is enabled and causing issues, user may need to:
    - Sign modules
    - Disable Secure Boot in BIOS
    - Use signed versions

20. **Performance tuning:**

    **Enable hugepages for better performance:**
    ```bash
    sudo sysctl vm.nr_hugepages=1024
    echo "vm.nr_hugepages=1024" | sudo tee -a /etc/sysctl.conf
    ```

    **Check CPU governor:**
    ```bash
    cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
    ```

    For virtualization, `performance` governor is recommended:
    ```bash
    sudo apt install cpufrequtils
    sudo cpufreq-set -g performance
    ```

21. **Report findings:**
    Summarize:
    - CPU virtualization support status
    - BIOS/UEFI virtualization enabled status
    - KVM modules loaded status
    - libvirt status
    - User group membership
    - Network configuration
    - Nested virtualization status
    - Storage pools status
    - Available resources
    - Any conflicts or issues
    - Recommendations

22. **Provide recommendations:**
    - Enable VT-x/AMD-V in BIOS if not enabled
    - Install KVM/QEMU if not present
    - Add user to libvirt and kvm groups
    - Set up default network
    - Enable nested virtualization if needed
    - Configure IOMMU for PCIe passthrough if needed
    - Install virt-manager for GUI management
    - Allocate sufficient resources
    - Resolve any conflicts (VirtualBox vs KVM)
    - Performance tuning suggestions

23. **Basic virtualization commands to share:**
    - `virsh list --all` - List all VMs
    - `virsh start <vm>` - Start a VM
    - `virsh shutdown <vm>` - Shutdown a VM
    - `virsh destroy <vm>` - Force stop a VM
    - `virsh console <vm>` - Connect to VM console
    - `virsh net-list` - List networks
    - `virsh pool-list` - List storage pools
    - `virt-manager` - Launch GUI
    - `virt-install` - Create new VM from command line

## Important notes:
- Virtualization must be enabled in BIOS/UEFI
- User must be in kvm and libvirt groups
- Log out and back in after adding to groups
- VirtualBox and KVM can conflict
- Nested virtualization is disabled by default
- IOMMU required for PCIe passthrough
- Secure Boot may prevent module loading
- Sufficient RAM and disk space needed
- Performance governor recommended for VMs
- Check if system is itself a VM before enabling nested virtualization
