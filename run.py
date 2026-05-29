"""
AI PR Review 助手 - 启动脚本
============================
快速启动开发服务器。
"""

import os
import sys


def main():
    # 确保在项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(project_root, "backend")
    os.chdir(backend_dir)
    sys.path.insert(0, backend_dir)

    # 加载 .env
    try:
        from dotenv import load_dotenv
        env_path = os.path.join(project_root, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"✅ 已加载环境变量: {env_path}")
        else:
            print(f"⚠️  未找到 .env 文件，请复制 .env.example → .env 并填入 API Key")
    except ImportError:
        print("⚠️  python-dotenv 未安装，跳过 .env 加载")

    # 检查必要配置
    github_token = os.getenv("GITHUB_TOKEN", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if not github_token:
        print("⚠️  GITHUB_TOKEN 未设置（公开仓库可以不设置，但有速率限制）")
    if not openai_key:
        print("❌ OPENAI_API_KEY 未设置！请设置环境变量或创建 .env 文件")
        print("   复制 .env.example → .env 并填入你的 API Key")
        sys.exit(1)

    import uvicorn
    from config import config

    print(f"""
╔══════════════════════════════════════════════╗
║         🤖 AI PR Review 助手 v1.0           ║
║                                              ║
║  模型: {config.openai_model:<36}║
║  地址: http://{config.host}:{config.port:<36}║
║                                              ║
╚══════════════════════════════════════════════╝
""")

    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
