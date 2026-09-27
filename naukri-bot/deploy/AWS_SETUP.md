# AWS + CI/CD Setup — beginner walkthrough (do once, ~45 min)

Push to `main` ⇒ GitHub Actions tests ⇒ builds Docker image ⇒ pushes to ECR ⇒
redeploys the bot on EC2 via SSM ⇒ publishes the dashboard HTML to S3.
The bot itself uploads `data.json` to S3 after every keyword cycle, so the
dashboard stays live with zero redeploys. Your local `nk` runner is untouched.

```
GitHub (push main) ──Actions──▶ ECR (image) ──SSM──▶ EC2 (bot, headless)
                        │                              │ data.json
                        └───────── S3 (dashboard) ◀─────┘
```

Expected cost: EC2 `t3.micro` (free-tier eligible first 12 months) + S3/ECR pennies.

## 1. AWS account + region

1. Create account at https://aws.amazon.com (needs a card; free tier covers a t3.micro).
2. Pick ONE region and use it everywhere. Recommended: **ap-south-1 (Mumbai)** — closest to Naukri + you.
3. Note it down: `AWS_REGION=ap-south-1`.

## 2. S3 bucket for the dashboard

Console → S3 → Create bucket:
- Name: something globally unique, e.g. `naukri-dashboard-imran2909`
- Region: your region. **Block all public access: OFF** (dashboard is public stats — no passwords ever go in it).
- After creation: Permissions → Bucket policy → paste (replace BUCKET):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow", "Principal": "*",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::BUCKET/*"
  }]
}
```

- Properties → Static website hosting → Enable, index document `index.html`.
- Note the website URL, e.g. `http://BUCKET.s3-website.ap-south-1.amazonaws.com`.

## 3. ECR repo for the bot image

Console → ECR → Create repository:
- Name: `naukri-bot`, region: yours. Note the URI, e.g.
  `123456789012.dkr.ecr.ap-south-1.amazonaws.com/naukri-bot`

## 4. EC2 server for the bot

Console → EC2 → Launch instance:
- Name: `naukri-bot`, AMI: **Ubuntu 22.04**, type: **t3.micro** (free tier), 30 GB gp3 disk.
- Key pair: create + download (for the one-time setup SSH only).
- Security group: allow SSH (port 22) **from your IP only**; outbound open (default). No inbound ports needed otherwise.
- Advanced → IAM instance profile: create role `naukri-bot-ec2` with managed policies
  `AmazonSSMManagedInstanceCore` + `AmazonEC2ContainerRegistryReadOnly`, plus an
  inline policy allowing `s3:PutObject` on `arn:aws:s3:::BUCKET/data.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow", "Action": "s3:PutObject",
    "Resource": "arn:aws:s3:::BUCKET/data.json"
  }]
}
```

- Launch, note the **instance ID** (`i-...`) and public IP.

One-time server prep over SSH:

```bash
ssh -i key.pem ubuntu@<EC2-IP>
sudo apt-get update && sudo apt-get install -y git
# paste deploy script:
curl -fsSL https://raw.githubusercontent.com/Imran2909/imran/main/naukri-bot/deploy/ec2-setup.sh | bash
# copy resume (run from YOUR pc):
scp -i key.pem "Imran Sutar - Full Stack Developer.pdf" ubuntu@<EC2-IP>:/opt/naukri-bot/naukri-bot/data/resume.pdf
```

## 5. IAM user for GitHub Actions (CI key)

Console → IAM → Users → Create `github-naukri-deployer`, no console access.
Attach a least-privilege inline policy (replace IDs/BUCKET/REGION):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {"Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*"},
    {"Effect": "Allow", "Action": ["ecr:*"],
     "Resource": "arn:aws:ecr:REGION:ACCOUNT:repository/naukri-bot"},
    {"Effect": "Allow", "Action": ["s3:PutObject", "s3:ListBucket"],
     "Resource": ["arn:aws:s3:::BUCKET", "arn:aws:s3:::BUCKET/*"]},
    {"Effect": "Allow", "Action": ["ssm:SendCommand", "ssm:GetCommandInvocation"],
     "Resource": "*"}
  ]
}
```

Security credentials → Create access key (CLI use) → save key + secret.

## 6. GitHub Secrets (repo → Settings → Secrets → Actions → New)

| Name | Value |
|---|---|
| `AWS_REGION` | `ap-south-1` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | from step 5 |
| `ECR_REPO` | full repo URI from step 3 |
| `S3_BUCKET` | bucket name from step 2 |
| `EC2_INSTANCE_ID` | `i-...` from step 4 |
| `NAUKRI_EMAIL` / `NAUKRI_PASSWORD` | your Naukri login |
| `OPENROUTER_API_KEY` | your key |

`.env` is git-ignored and NEVER committed — the workflow writes it on the server from these secrets.

## 7. First deploy

```bash
cd C:\Users\Hp\Desktop\imran
git add naukri-bot .github
git status   # MUST NOT list naukri-bot/.env, data/*.db, bot-profile/
git commit -m "Naukri bot + dashboard + CI/CD"
git push origin main
```

Watch: GitHub repo → Actions tab → the run → green checks. Then:
- Dashboard: your S3 website URL (shows data after the bot's first cycle uploads `data.json`).
- Bot logs: SSM Run Command history, or SSH once and `docker logs -f naukri-bot-bot-1`.

## 8. Honest caveats

- EC2 runs **headless** Chromium. Naukri detects headless browsers more often than your local headed one — if the cloud bot hits repeated captchas it sleeps 60 min and retries. Keep local `nk` as your primary applier; treat the server as a second shift.
- First cloud login uses your env creds; if Naukri challenges it, check container logs.
- Dashboard is public (job titles/companies only — no credentials). For private stats later: CloudFront + signed URLs.
- Upgrade path: move `.env` secrets into SSM Parameter Store instead of the deploy command.

## 9. Troubleshooting

- Actions red on `test`: read the failing step; usually a Python syntax error — fix, push again.
- `ECR login failed`: wrong region in secret or policy typo.
- `SSM send-command` TargetNotHealthy: instance role missing `AmazonSSMManagedInstanceCore`, or instance just launched (wait 3 min).
- `docker compose: command not found` on EC2: re-run `ec2-setup.sh`.
- Dashboard shows "loading…": bot hasn't uploaded `data.json` yet (first cycle) — check bot logs.
