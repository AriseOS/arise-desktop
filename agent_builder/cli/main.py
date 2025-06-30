#!/usr/bin/env python3

from fastapi import FastAPI
import uvicorn

app = FastAPI(title="AgentBuilder Server")

@app.get("/")
async def root():
    return {"message": "AgentBuilder Server is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)