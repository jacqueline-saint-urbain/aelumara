# Island chat

This branch only exists to hold the island's in-game chat. The chat lives in the comments of its pull request, which must never be merged or closed.

- The island page (https://aelumara.pages.dev/, 💬 tab) reads the comments without a token, because this repo is public.
- Posting needs a fine-grained GitHub token limited to `jacqueline-saint-urbain/aelumara` with **Pull requests: Read and write**.
- Each message is a comment holding a ```trio block (trio/1 envelope: `from`, `to`, `human`, `body`, `id`). Text outside the block is ignored by parsers.
