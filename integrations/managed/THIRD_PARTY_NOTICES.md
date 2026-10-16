# Third-party notices

The launcher is MIT-licensed. It contains no third-party JavaScript dependencies.
It downloads the following components into a private installation directory:

| Component | License |
| --- | --- |
| uv | Apache-2.0 OR MIT |
| Python (python-build-standalone) | PSF-2.0 |
| Qdrant Memory Runtime | MIT |
| CPU embedding model, Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q | Apache-2.0 |

Versions, download locations and artifact hashes are recorded in
`bootstrap.mjs`, `runtime.json` and `requirements.lock`. Runtime verifies the
model revision and artifact hashes. Downloaded dependencies retain their
upstream licenses in the private Python environment. This package does not
contain Python, uv, model weights, user profiles or memory data.
