#!/bin/bash
# Oracle Cloud "Initialization script" for the SHIFTGUARD judge VM (Ubuntu 24.04, ARM or x86).
# Installs Docker Engine + the compose plugin and opens ports 80/443 in the host firewall.
# Oracle's Ubuntu images block everything except SSH in iptables, so this is also needed
# besides the VCN security-list rules. The app itself is deployed later over SSH.
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git iptables-persistent
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
netfilter-persistent save
# 2 GB swap as headroom for image builds.
if [ ! -f /swapfile ]; then fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
touch /var/lib/shiftguard-cloud-init-done
