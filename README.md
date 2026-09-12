# sc

personal task scheduler + headless browser automation service.

## setup

open your existing debian lxc shell in proxmox, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/IAndrexI/SC/main/install.sh | bash
```

open the ui → import session → add targets → set time → done.

## stack

- python / fastapi
- playwright (chromium)
- apscheduler
- debian 12
