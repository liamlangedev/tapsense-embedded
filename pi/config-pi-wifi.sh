#!/bin/sh
set -eu
image=/dev/mmcblk0
offset=8388608
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

[ -f "$image" ] || { echo "Pi image not found at $image" >&2; exit 1; }
[ "$(stat -c %s "$image")" -ge 2785017856 ] || { echo "Pi image size changed; refusing" >&2; exit 1; }

mcopy -i "$image@@$offset" ::/network-config "$work/network-config.original"
mcopy -o -i "$image@@$offset" ::/network-config "$work/network-config.bak"
cat > "$work/network-config" <<'EOF'
network:
  version: 2
  wifis:
    wlan0:
      dhcp4: true
      optional: true
      access-points:
        "Netzwerk": {}
EOF
mcopy -o -i "$image@@$offset" "$work/network-config" ::/network-config
sync
mtype -i "$image@@$offset" ::/network-config
