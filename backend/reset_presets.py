import asyncio
import os
import sys

# 将工程根目录加入 Python 路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.db.engine import async_session
from backend.db.seed import initialize_user_data

async def main():
    user_id = "ea61d33b-89e6-4c53-b4ea-e712e09cc23f"
    tenant_id = "de7bd136-9f7d-436b-8807-cf2715014a9e"
    
    print(f"正在重置用户 {user_id} 的预设配置...")
    
    async with async_session() as db:
        try:
            await initialize_user_data(db, user_id, tenant_id)
            await db.commit()
            print("✅ 预设重置成功！")
        except Exception as e:
            await db.rollback()
            print(f"❌ 重置失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
