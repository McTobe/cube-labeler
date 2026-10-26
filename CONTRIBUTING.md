# Contributing to Cube Labeler

Thanks for helping out. Bug reports, ideas and pull requests are all welcome.

## Reporting bugs and ideas

Open an [issue](https://github.com/McTobe/cube-labeler/issues/new/choose) and pick the bug or idea form. For bugs, the version, whether you use the web or desktop app, and your browser or Windows version help a lot. Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Setting up

```bash
git clone https://github.com/McTobe/cube-labeler.git
cd cube-labeler
pip install -r requirements.txt -c constraints.txt
python main.py              # desktop app
python web/serve.py         # web app on http://localhost:8000
```

The web app runs the Python code in `core/` in the browser through Pyodide, so a change to the label code affects both apps. See [web/README.md](web/README.md) for how the web side is put together.

## Before you open a pull request

- Keep it focused on one change.
- Add or update tests where it makes sense, and check that they pass:

  ```bash
  python -m unittest discover tests
  cd web && npm ci && npm test     # after python web/build.py
  ```

- For UI changes, add a screenshot to the pull request. Page layouts follow [docs/DESIGN.md](docs/DESIGN.md).
- Match the style of the code around your change.

CI runs the same tests on Windows and Linux for every pull request.

## License of contributions

By contributing, you agree that your contribution is released under the same license as the project (see [LICENSE](LICENSE)).
