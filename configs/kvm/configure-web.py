from pathlib import Path
import secrets,subprocess
p=Path('/etc/nginx/sites-enabled/default')
p.write_text('''server {
 listen 80;
 return 301 https://$host$request_uri;
}
server {
 listen 443 ssl;
 ssl_certificate /etc/kvmd/nginx/ssl/server.crt;
 ssl_certificate_key /etc/kvmd/nginx/ssl/server.key;
 include /etc/kvmd/nginx/kvmd.ctx-server.conf;
}
''')
Path('/etc/nginx/conf.d/kvmd.conf').write_text(Path('/etc/kvmd/nginx/kvmd.ctx-http.conf').read_text())
Path('/etc/kvmd/nginx/ssl').mkdir(exist_ok=True)
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout','/etc/kvmd/nginx/ssl/server.key','-out','/etc/kvmd/nginx/ssl/server.crt','-days','365','-subj','/CN=gtw360'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
password=secrets.token_urlsafe(12)
subprocess.run(['htpasswd','-ciB','/etc/kvmd/htpasswd','admin'],input=password+'\n',text=True,check=True)
p=Path('/root/gtw360-kvm-login');p.write_text('admin\n'+password+'\n');p.chmod(0o600)
Path('/etc/systemd/system/kvmd.service').write_text('''[Unit]
Description=GTW360 KVMD
After=network.target gtw360-hid-test.service
Requires=gtw360-hid-test.service
[Service]
ExecStart=/opt/gtw360/venv/bin/kvmd --run
RuntimeDirectory=kvmd
RuntimeDirectoryMode=0775
Group=www-data
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
''')

Path('/etc/kvmd/vnc/ssl').mkdir(parents=True, exist_ok=True)
for name in ['server.crt', 'server.key']:
    Path('/etc/kvmd/vnc/ssl', name).symlink_to('/etc/kvmd/nginx/ssl/'+name)
