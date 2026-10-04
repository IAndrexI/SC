# SnapStreak — Windows Extension Variant

The **Windows Extension Variant** runs directly on your Windows PC using your daily consumer browser (Brave or Google Chrome). 

### Why Use This Variant?
- **Zero Bot/Datacenter Bans**: Uses your physical PC's residential IP and genuine browser profile.
- **Visual HUD**: Floating HUD on Snapchat Web showing live streak automation progress, timer countdowns, and quick controls.
- **Webcam Emulation**: Automatically injects a live SJSU Meteorology camera feed so Snapchat's camera requirements are met without needing a physical webcam.

---

## Quick Setup

### 1. Install the Extension
1. Double-click `install_extension.bat`.
   * It will open your browser's extensions page (`brave://extensions` or `chrome://extensions`).
2. In the top right, turn **Developer mode** **ON**.
3. In the top left, click **Load unpacked**.
4. Select the `extension` folder located inside this directory:
   ```
   windows-extension\extension
   ```

### 2. Launch Snapchat with Live Camera Feed
Double-click `launch_extension.bat`.
* This will launch your browser with the live webcam feed hook, bypass background crash recovery bubbles, and open `https://web.snapchat.com`.
* Log in if you aren't already logged in.

---

## Automation & Auto-Start (Optional)

If you want your Windows PC to run this completely hands-free on startup:
1. **Enable Windows Auto-Login**:
   * Right-click `enable_autologon.bat` and run as Administrator.
   * This uses Microsoft Sysinternals `Autologon.exe` to automatically sign into your Windows desktop on reboot.
2. **Auto-Launch on Boot**:
   * Press `Win + R`, type `shell:startup`, and press Enter.
   * Create a shortcut to `launch_extension.bat` inside that Startup folder.
