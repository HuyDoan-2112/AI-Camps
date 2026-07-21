# AI-Camps
An AI-powered academic advising chatbot that helps engineering students build realistic, transfer-aligned course plans using prerequisites, program requirements, and historical course availability.

rag-app/
├── src/
│   ├── config.py       ← all settings, env vars in one place
│   ├── chunker.py      ← text splitting
│   ├── embeddings.py   ← OpenAI embedding calls
│   ├── vectorstore.py  ← ChromaDB read/write
│   ├── retriever.py    ← query → top-k chunks
│   └── generator.py    ← GPT-4o + ConversationHistory
├── ingest.py           ← CLI: load docs into vector store
├── chat.py             ← CLI: multi-turn chat (replaces query.py)
├── bot.py              ← platform adapter (Slack/Discord/Telegram/API)
├── .github/
│   └── ISSUE_TEMPLATE/ ← bug report + feature request templates
├── README.md
└── .env.example
