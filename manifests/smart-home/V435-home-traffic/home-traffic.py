#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
home-traffic — analyze home network traffic from PCAP files.
Shows per-device bandwidth, connection pairs, DNS queries, and suspicious ports.
"""

import json
import socket
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import click
import dpkt
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

# Ports considered "suspicious" for a typical home network
SUSPICIOUS_PORTS = {
    22, 23, 25, 4444, 31337, 1080, 8080, 3128,
    135, 137, 138, 139, 445,   # SMB/NetBIOS
    1194, 1723,                 # VPN
    6881, 6882, 6883,           # BitTorrent
}

# Well-known service port names
_SERVICE_NAMES = {
    20: "FTP-data", 21: "FTP", 22: "SSH", 23: "Telnet",
    25: "SMTP", 53: "DNS", 67: "DHCP-srv", 68: "DHCP-cli",
    80: "HTTP", 110: "POP3", 123: "NTP", 143: "IMAP",
    443: "HTTPS", 465: "SMTPS", 587: "SMTP-sub", 993: "IMAPS",
    995: "POP3S", 1194: "OpenVPN", 3389: "RDP", 5353: "mDNS",
    8080: "HTTP-alt", 8443: "HTTPS-alt",
}


def _ip(addr: bytes) -> str:
    try:
        if len(addr) == 4:
            return socket.inet_ntop(socket.AF_INET, addr)
        elif len(addr) == 16:
            return socket.inet_ntop(socket.AF_INET6, addr)
    except Exception:
        pass
    return addr.hex()


def _is_private(ip_str: str) -> bool:
    """Rough check whether an IPv4 address is in RFC-1918 space."""
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
        return (
            a == 10
            or (a == 172 and 16 <= b <= 31)
            or (a == 192 and b == 168)
            or a == 127
        )
    except ValueError:
        return False


def _port_label(port: int) -> str:
    name = _SERVICE_NAMES.get(port)
    return f"{port}/{name}" if name else str(port)


def analyze_home_traffic(path: Path, top_n: int = 10) -> dict:
    """
    Parse a PCAP and return home-network-focused statistics:
      - total_packets, total_bytes, duration_seconds
      - device_traffic: bytes sent/received per private IP
      - connection_pairs: top (src_ip, dst_ip) pairs
      - dns_queries: most queried domain names
      - service_ports: traffic volume per destination port
      - suspicious_alerts: list of {src, dst, port, packets}
    """
    total_packets = 0
    total_bytes = 0
    first_ts: Optional[float] = None
    last_ts: Optional[float] = None

    # device → {"sent": bytes, "received": bytes}
    device_traffic: dict = defaultdict(lambda: {"sent": 0, "received": 0})
    # (src_ip, dst_ip) → packet count
    pair_counter: Counter = Counter()
    # dst_port → packet count
    port_counter: Counter = Counter()
    # DNS query names
    dns_queries: Counter = Counter()
    # suspicious: (src_ip, dst_ip, port) → packets
    suspicious: Counter = Counter()

    with open(path, "rb") as f:
        reader = dpkt.pcap.Reader(f)

        for ts, buf in reader:
            total_packets += 1
            total_bytes += len(buf)

            if first_ts is None:
                first_ts = ts
            last_ts = ts

            try:
                eth = dpkt.ethernet.Ethernet(buf)
            except Exception:
                continue

            # Unwrap IP
            if isinstance(eth.data, dpkt.ip.IP):
                ip_pkt = eth.data
            elif isinstance(eth.data, dpkt.ip6.IP6):
                ip_pkt = eth.data
            else:
                continue

            src_ip = _ip(ip_pkt.src)
            dst_ip = _ip(ip_pkt.dst)
            pkt_len = len(buf)

            # Per-device bandwidth
            if _is_private(src_ip):
                device_traffic[src_ip]["sent"] += pkt_len
            if _is_private(dst_ip):
                device_traffic[dst_ip]["received"] += pkt_len

            # Connection pairs (private ↔ any)
            if _is_private(src_ip) or _is_private(dst_ip):
                pair_counter[(src_ip, dst_ip)] += 1

            # Transport layer
            transport = ip_pkt.data
            if isinstance(transport, (dpkt.tcp.TCP, dpkt.udp.UDP)):
                try:
                    dport = transport.dport
                    port_counter[dport] += 1

                    if dport in SUSPICIOUS_PORTS:
                        suspicious[(src_ip, dst_ip, dport)] += 1

                    # DNS (UDP port 53)
                    if isinstance(transport, dpkt.udp.UDP) and (dport == 53 or transport.sport == 53):
                        try:
                            dns = dpkt.dns.DNS(transport.data)
                            for q in dns.qd:
                                dns_queries[q.name] += 1
                        except Exception:
                            pass
                except Exception:
                    pass

    duration = (last_ts - first_ts) if (first_ts is not None and last_ts is not None) else 0.0

    # Format device traffic
    devices_sorted = sorted(
        device_traffic.items(),
        key=lambda kv: kv[1]["sent"] + kv[1]["received"],
        reverse=True,
    )[:top_n]

    # Format connection pairs
    top_pairs = [
        {"src": src, "dst": dst, "packets": cnt}
        for (src, dst), cnt in pair_counter.most_common(top_n)
    ]

    # Format port usage
    top_ports = [
        {"port": _port_label(port), "packets": cnt}
        for port, cnt in port_counter.most_common(top_n)
    ]

    # Format suspicious
    suspicious_alerts = [
        {"src": src, "dst": dst, "port": _port_label(port), "packets": cnt}
        for (src, dst, port), cnt in suspicious.most_common(20)
    ]

    return {
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "duration_seconds": round(duration, 6),
        "device_traffic": [
            {"ip": ip, "sent_bytes": v["sent"], "received_bytes": v["received"]}
            for ip, v in devices_sorted
        ],
        "connection_pairs": top_pairs,
        "service_ports": top_ports,
        "dns_queries": [[name, cnt] for name, cnt in dns_queries.most_common(top_n)],
        "suspicious_alerts": suspicious_alerts,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def cli(ctx, verbose: bool) -> None:
    """home-traffic — analyze home network traffic from PCAP files."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command("run")
@click.argument("pcap_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--top", "-n", default=10, show_default=True,
              help="Number of top entries to show per category")
@click.option("--json-only", "-j", is_flag=True, help="Output raw JSON only (no rich tables)")
@click.option("--dry-run", is_flag=True, help="Validate file only, do not parse packets")
@click.pass_context
def run(ctx, pcap_file: str, top: int, json_only: bool, dry_run: bool) -> None:
    """Parse PCAP_FILE and show home-network traffic analysis."""
    path = Path(pcap_file)

    if dry_run:
        result = {"dry_run": True, "file": str(path), "size_bytes": path.stat().st_size}
        click.echo(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, indent=2))
        return

    try:
        summary = analyze_home_traffic(path, top_n=top)
    except dpkt.dpkt.NeedData as exc:
        console.print(f"[red]Error parsing PCAP:[/red] {exc}")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[red]Unexpected error:[/red] {exc}")
        sys.exit(1)

    if json_only:
        click.echo(json.dumps({"status": "ok", "data": summary}, ensure_ascii=False, indent=2))
        return

    # ── Rich display ──────────────────────────────────────────────────────────
    console.print(Panel(
        f"[bold]{path.name}[/bold]\n"
        f"Packets: [cyan]{summary['total_packets']:,}[/cyan]   "
        f"Bytes: [cyan]{summary['total_bytes']:,}[/cyan]   "
        f"Duration: [cyan]{summary['duration_seconds']:.3f}s[/cyan]",
        title="home-traffic Summary"
    ))

    # Device traffic
    dev_table = Table(title=f"Top {top} Devices by Traffic", box=box.SIMPLE_HEAVY)
    dev_table.add_column("IP Address", style="cyan")
    dev_table.add_column("Sent (bytes)", justify="right")
    dev_table.add_column("Received (bytes)", justify="right")
    dev_table.add_column("Total (bytes)", justify="right", style="yellow")
    for dev in summary["device_traffic"]:
        total = dev["sent_bytes"] + dev["received_bytes"]
        dev_table.add_row(
            dev["ip"],
            f"{dev['sent_bytes']:,}",
            f"{dev['received_bytes']:,}",
            f"{total:,}",
        )
    console.print(dev_table)

    # Connection pairs
    pair_table = Table(title=f"Top {top} Connection Pairs", box=box.SIMPLE_HEAVY)
    pair_table.add_column("Source", style="cyan")
    pair_table.add_column("Destination", style="magenta")
    pair_table.add_column("Packets", justify="right", style="yellow")
    for p in summary["connection_pairs"]:
        pair_table.add_row(p["src"], p["dst"], str(p["packets"]))
    console.print(pair_table)

    # Service ports
    port_table = Table(title=f"Top {top} Destination Ports", box=box.SIMPLE_HEAVY)
    port_table.add_column("Port/Service", style="cyan")
    port_table.add_column("Packets", justify="right", style="yellow")
    for entry in summary["service_ports"]:
        port_table.add_row(entry["port"], str(entry["packets"]))
    console.print(port_table)

    # DNS queries
    if summary["dns_queries"]:
        dns_table = Table(title=f"Top {top} DNS Queries", box=box.SIMPLE_HEAVY)
        dns_table.add_column("Domain", style="cyan")
        dns_table.add_column("Queries", justify="right", style="yellow")
        for name, cnt in summary["dns_queries"]:
            dns_table.add_row(name, str(cnt))
        console.print(dns_table)

    # Suspicious alerts
    if summary["suspicious_alerts"]:
        alert_table = Table(title="Suspicious Port Alerts", box=box.SIMPLE_HEAVY, style="red")
        alert_table.add_column("Source", style="cyan")
        alert_table.add_column("Destination", style="magenta")
        alert_table.add_column("Port", style="red")
        alert_table.add_column("Packets", justify="right")
        for alert in summary["suspicious_alerts"]:
            alert_table.add_row(alert["src"], alert["dst"], alert["port"], str(alert["packets"]))
        console.print(alert_table)
    else:
        console.print("[green]No suspicious port activity detected.[/green]")

    click.echo(json.dumps({"status": "ok", "data": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
