# CI/CD deployment

The GitHub Actions workflow runs Ruff and pytest for pull requests and pushes. A
successful push to `main` or `master` builds a wheel and deploys it to the VPS.
Application secrets remain in `/etc/tgwhisper.env` on the server.

Each deployment creates an isolated release under `/opt/tgwhisper/releases` and
atomically updates `/opt/tgwhisper/current`. The deployment script waits for the
systemd service to remain active and restores the previous release if startup
fails. The five most recent successful release directories are retained.

## 1. Create the deployment account on the VPS

Run as root:

```bash
adduser --disabled-password --gecos "" deploy
install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
install -d -o deploy -g deploy -m 755 /var/lib/tgwhisper-deploy/incoming
```

Generate a dedicated key on the local Windows computer in PowerShell:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\tgwhisper_deploy" -C "github-actions-tgwhisper"
Get-Content "$env:USERPROFILE\.ssh\tgwhisper_deploy.pub"
```

Leave the key passphrase empty: GitHub Actions must use this dedicated key
non-interactively. The account is limited below to the single root-owned deployment
script.

Copy the printed public key into `/home/deploy/.ssh/authorized_keys` on the VPS,
then set its ownership and permissions:

```bash
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
```

Test the key from PowerShell before continuing:

```powershell
ssh -i "$env:USERPROFILE\.ssh\tgwhisper_deploy" deploy@VPS_IP
```

## 2. Install the deployment files on the VPS

Upload the three files from the repository:

```powershell
scp deploy/deploy-tgwhisper deploy/tgwhisper.service deploy/tgwhisper.sudoers root@VPS_IP:/tmp/
```

Run on the VPS as root:

```bash
install -o root -g root -m 755 /tmp/deploy-tgwhisper /usr/local/sbin/deploy-tgwhisper
install -o root -g root -m 644 /tmp/tgwhisper.service /etc/systemd/system/tgwhisper.service
install -o root -g root -m 440 /tmp/tgwhisper.sudoers /etc/sudoers.d/tgwhisper-deploy
visudo -cf /etc/sudoers.d/tgwhisper-deploy
systemctl daemon-reload
```

The service file now points to `/opt/tgwhisper/current`, which will be created by
the first automated deployment. The already running process continues to use the
old executable after `daemon-reload`; do not restart it manually before the first
deployment.

## 3. Publish the repository to GitHub

Create an empty private repository on GitHub. From PowerShell in the local
TgWhisper directory, replace the example URL and run:

```powershell
git remote add origin git@github.com:YOUR_ACCOUNT/tgwhisper.git
git push -u origin master
```

The workflow also supports `main` if the branch is renamed later.

## 4. Configure the GitHub production environment

In the repository, open **Settings → Environments → New environment** and create
an environment named `production`. Add these environment secrets:

| Secret | Value |
|---|---|
| `VPS_HOST` | VPS IP address or DNS name |
| `VPS_SSH_PRIVATE_KEY_B64` | Base64-encoded bytes of the private `tgwhisper_deploy` key |
| `VPS_KNOWN_HOSTS` | Verified SSH host-key entry for the VPS |

Encode the private key as one Base64 line in PowerShell for copying into GitHub:

```powershell
[Convert]::ToBase64String(
    [IO.File]::ReadAllBytes("$env:USERPROFILE\.ssh\tgwhisper_deploy")
)
```

Obtain the server's Ed25519 host public key from the VPS console, where the host
identity is already trusted:

```bash
cat /etc/ssh/ssh_host_ed25519_key.pub
```

Create `VPS_KNOWN_HOSTS` as one line, replacing `VPS_IP` and using the key output:

```text
VPS_IP ssh-ed25519 AAAAC3...server-public-key...
```

Do not store the Telegram token or OpenAI key in GitHub. They are loaded from
`/etc/tgwhisper.env` by systemd.

## 5. Run the first deployment

Commit the CI/CD files and push them:

```powershell
git add .github/workflows/ci-cd.yml deploy docs/CI_CD.md
git commit -m "Add CI/CD deployment"
git push
```

Open the repository's **Actions** tab and watch the `CI/CD` workflow. On success,
verify the VPS:

```bash
systemctl status tgwhisper --no-pager -l
readlink -f /opt/tgwhisper/current
journalctl -u tgwhisper -n 30 --no-pager -l
```

Every later push to `main` or `master` follows the same test-and-deploy process.
