# sc

personal task scheduler + headless browser automation service.
runs on a proxmox lxc, accessible via local web ui.

## setup

```bash
# on proxmox host
bash -c "$(curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/proxmox-lxc.sh)"
```

open the ui → import session → add targets → set time → done.

## stack

- python / fastapi
- playwright (chromium)
- apscheduler
- debian 12 lxc (~512mb ram)
