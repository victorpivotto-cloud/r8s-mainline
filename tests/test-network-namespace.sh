#!/bin/sh
# Run only inside an isolated network namespace; never change host routes.
set -eu
ns="r8s-qual-$$"
dir=$(mktemp -d /run/r8s-network-test.XXXXXX)
server_pid=
cleanup() {
    [ -z "$server_pid" ] || kill "$server_pid" 2>/dev/null || true
    ip netns del "$ns" 2>/dev/null || true
    rm -f "$dir/index.html"
    rmdir "$dir" 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM
before=$(ip route show table main | sha256sum)
ip netns add "$ns"
ip -n "$ns" link set lo up
ip -n "$ns" addr add 192.0.2.20/32 dev lo
ip -n "$ns" route add 198.51.100.0/24 dev lo table 420
ip -n "$ns" rule add priority 100 from 192.0.2.20/32 lookup 420
ip -n "$ns" route get 198.51.100.9 from 192.0.2.20 | grep -q 'table 420'
echo 'PASS: IPv4 source policy selects table 420'
ip -n "$ns" -6 addr add 2001:db8::20/128 dev lo nodad
ip -n "$ns" -6 route add 2001:db8:1::/64 dev lo table 421
ip -n "$ns" -6 rule add priority 100 from 2001:db8::20/128 lookup 421
ip -n "$ns" -6 route get 2001:db8:1::9 from 2001:db8::20 | grep -q 'table 421'
echo 'PASS: IPv6 source policy selects table 421'
printf 'r8s-nft-redirect-ok\n' > "$dir/index.html"
ip netns exec "$ns" busybox httpd -f -p 18081 -h "$dir" &
server_pid=$!
ip netns exec "$ns" nft -f - <<'NFT'
table inet r8s_test {
    chain output {
        type nat hook output priority -100; policy accept;
        tcp dport 18080 redirect to :18081
    }
}
NFT
result=$(ip netns exec "$ns" curl --silent --show-error --fail --retry 2 --retry-connrefused --max-time 5 http://127.0.0.1:18080/)
[ "$result" = r8s-nft-redirect-ok ]
echo 'PASS: HTTP packet redirected 18080 -> 18081 by nftables'
ip netns exec "$ns" conntrack -L >/dev/null
echo 'PASS: conntrack netlink query'
after=$(ip route show table main | sha256sum)
[ "$before" = "$after" ]
echo 'PASS: management routing unchanged'
