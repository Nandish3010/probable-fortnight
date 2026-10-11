# Trying it in GitHub Codespaces

Open the repo on GitHub, Code → Codespaces → Create. The devcontainer installs everything and runs
`make generate`. Then, in two terminals:

```
make api
NEXT_PUBLIC_TAAL_API_URL=https://<your codespace name>-8080.app.github.dev make web
```

Port 8080 is forwarded as public by the devcontainer so the browser can reach the API; port 3000
opens automatically. Stop the Codespace when you are done.
