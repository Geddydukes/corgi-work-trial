# GitHub Repository Setup Instructions

## Option 1: Using GitHub Web Interface (Recommended)

1. Go to https://github.com/new
2. Repository name: `Corgi` (or your preferred name)
3. Set visibility to **Private**
4. **DO NOT** initialize with README, .gitignore, or license (we already have these)
5. Click "Create repository"

6. After creating, run these commands in your terminal:

```bash
cd <project-directory>
git remote add origin https://github.com/YOUR_USERNAME/<repository-name>.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

## Option 2: Using GitHub CLI (if installed)

```bash
cd <project-directory>
gh repo create <repository-name> --private --source=. --remote=origin --push
```

## Option 3: Using GitHub API with Personal Access Token

1. Create a Personal Access Token at: https://github.com/settings/tokens
   - Select scope: `repo` (full control of private repositories)

2. Export the token:
```bash
export GITHUB_TOKEN=your_token_here
```

3. Run the setup script:
```bash
cd <project-directory>
./setup_github_repo.sh <repository-name> YOUR_GITHUB_USERNAME
```

## After Setup

Once the repository is created and pushed, you can:

- View it at: `https://github.com/YOUR_USERNAME/<repository-name>`
- Clone it on another computer: `git clone https://github.com/YOUR_USERNAME/<repository-name>.git`
- Pull updates: `git pull origin main`
- Push changes: `git push origin main`

## Current Status

✅ All code is committed locally
✅ Branch renamed to `main`
✅ Ready to push to remote

