import uwuify
import uvicorn

from typing import Optional
from starlette.requests import Request
from helpers import TikTok, Snap, SnapUser, Roblox

from fastapi.security import APIKeyHeader
from fastapi.openapi.utils import get_openapi
from fastapi import FastAPI, Depends, HTTPException, Request


class CustomApp(FastAPI):
    def __init__(self):
        super().__init__(redoc_url="/", docs_url="/admin", title="Pretend API")

        self.tiktok = TikTok()
        self.roblox = Roblox()

    def custom_openapi(self):
        if self.openapi_schema:
            return self.openapi_schema

        openapi_schema = get_openapi(
            title="Pretend Api",
            version="1.1.0",
            routes=self.routes,
        )
        openapi_schema["info"]["x-logo"] = {
            "url": "https://cdn.discordapp.com/banners/1005150492382478377/a_b3372e8671e46641ddd8ffb01c93dd72.gif?size=1024"
        }
        self.openapi_schema = openapi_schema


app = CustomApp()


class AuthScheme(APIKeyHeader):
    async def __call__(self, request: Request) -> Optional[str]:
        key = await super().__call__(request)
        if key != "5447e58a8d549945b51608923f2f748506defafc68a711cf860e377327580873":
            raise HTTPException(status_code=403, detail="Unauthorized")

        return key


auth_scheme = AuthScheme(name="Authorization")


@app.get("/uwu", description="uwuify your messages")
async def uwu(message: str):
    return {"message": uwuify.uwu(message)}


@app.get("/snapchat", description="get an user's snapchat profile info")
async def snapchat(username: str, token=Depends(auth_scheme)):
    return await SnapUser().scrape(username)


@app.get("/snapstory", description="get an user's snapchat stories")
async def snapstory(username: str, token=Depends(auth_scheme)):
    return await Snap().scrape(username)


@app.get("/tiktok", description="get tiktok user from username")
async def tiktok(username: str, token=Depends(auth_scheme)):
    return await app.tiktok.scrape(username)


@app.get("/roblox", description="get roblox profile from username")
async def roblox(username: str, token=Depends(auth_scheme)):
    return await app.roblox.scrape(username)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5500, reload=True)
