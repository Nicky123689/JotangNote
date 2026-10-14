"""JotangNote 后端（FastAPI）

启蒙篇：先跑通一个最小 Web 应用——浏览器访问 http://localhost:8080/hello
返回 Hello World From Web Application!

后续入门篇/进阶篇会在这里逐步加入 MySQL、Redis、RabbitMQ 与 AI 接口。
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse

app = FastAPI(
    title="JotangNote",
    description="焦糖工作室招新 · 后端项目（启蒙篇起步）",
    version="0.1.0",
)


@app.get("/hello", response_class=PlainTextResponse)
def hello() -> str:
    """启蒙篇要求：访问 /hello 返回这句固定文本。"""
    return "Hello World From Web Application!"


@app.get("/", response_class=JSONResponse)
def index() -> dict:
    """顺便给个首页，方便确认服务活着。"""
    return {
        "name": "JotangNote",
        "stage": "启蒙篇",
        "endpoints": ["/hello", "/docs"],
    }
