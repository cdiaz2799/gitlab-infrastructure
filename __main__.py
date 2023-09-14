"""A DigitalOcean Python Pulumi program"""

import pulumi
import pulumi_cloudflare as cf
import pulumi_digitalocean as do

# Setup Vars
app_name = "gitlab"
region = "sfo3"
vpc_name = f"cdiaz-cloud-vpc-{region}"
image = "ubuntu-22-04-x64"
size = "s-4vcpu-16gb-amd"
tags = [
    app_name,
]

# Define Ingress
dns_dict = {
    app_name: 80,
    "pages": 10080,
    f"{app_name}-ssh": 22,
}

# Get VPC
vpc = do.get_vpc(name=vpc_name)

# Setup Project
gitlab_project = do.Project(
    f"{app_name}-project",
    name=app_name,
    description=f"{app_name} Resources",
    environment="Production",
    purpose="Web Application",
)

# Setup VM / Droplet
gitlab_vm = do.Droplet(
    f"{app_name}-vm-1",
    name=f"{app_name}-vm-1",
    image=image,
    region=region,
    size=size,
    monitoring=True,
    vpc_uuid=vpc.id,
    tags=tags,
)

# Setup Firewall
gitlab_firewall = do.Firewall(
    f"{app_name}-firewall",
    name=f"{app_name}-firewall",
    droplet_ids=[gitlab_vm.id],
    # Forbid all inbound traffic, ingress is managed by Cloudflare Tunnels
    inbound_rules=[],
    outbound_rules=[
        do.FirewallOutboundRuleArgs(
            protocol="icmp",
            port_range="1-65535",
            destination_addresses=[
                "0.0.0.0/0",
                "::/0",
            ],
        ),
        do.FirewallOutboundRuleArgs(
            protocol="tcp",
            port_range="1-65535",
            destination_addresses=[
                "0.0.0.0/0",
                "::/0",
            ],
        ),
        do.FirewallOutboundRuleArgs(
            protocol="udp",
            port_range="1-65535",
            destination_addresses=[
                "0.0.0.0/0",
                "::/0",
            ],
        ),
    ],
)

# Create Tunnel
cf_config = pulumi.Config("cf")

gitlab_tunnel = cf.Tunnel(
    f"{app_name}-tunnel",
    name=app_name,
    account_id=cf_config.get_secret("accountId"),
    secret="",
    opts=pulumi.ResourceOptions(protect=True, depends_on=[gitlab_vm]),
)

# Create DNS Record and Ingress
dns_records = []
ingress_rules = []

for dns_name, port in dns_dict.items():
    record_name = dns_name
    dns_record = cf.Record(
        resource_name=f"{record_name}-dns",
        zone_id=cf_config.get_secret("zoneId"),
        name=record_name,
        type="CNAME",
        value=gitlab_tunnel.cname,
        proxied=True,
        comment="Managed by Pulumi",
    )
    dns_records.append(dns_record)

    service = f"http://localhost:{port}" if port != 22 else "ssh://localhost:22"
    ingress_rules.append(
        cf.TunnelConfigConfigIngressRuleArgs(
            hostname=dns_record.hostname,
            service=service,
        ),
    )

# Append 404
ingress_rules.append(cf.TunnelConfigConfigIngressRuleArgs(service="http_status:404"))

# Setup Tunnel Config
gitlab_tunnel_config = cf.TunnelConfig(
    resource_name=f"{app_name}-tunnel-config",
    account_id=gitlab_tunnel.account_id,
    tunnel_id=gitlab_tunnel.id,
    config=cf.TunnelConfigConfigArgs(ingress_rules=ingress_rules),
)

hostnames = [record.hostname for record in dns_records]

# Outputs
pulumi.export("DigitalOcean Project:", gitlab_project.name)
pulumi.export("VM public IP:", gitlab_vm.ipv4_address)
pulumi.export("Gitlab URLs:", hostnames)
