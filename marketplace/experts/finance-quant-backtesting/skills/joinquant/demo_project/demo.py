def main():
    print("🤖 JoinQuant (jqdatasdk) 实际接口调用演示")
    try:
        from jqdatasdk import auth, get_price
        print("注意：JQData 需要账号密码认证...")
        # auth('YOUR_USERNAME', 'YOUR_PASSWORD')
        print("✅ JQData API 导入成功。实际使用前请取消注释并配置 auth()")
    except ImportError:
        print("❌ 未安装 jqdatasdk")
    except Exception as e:
        print(f"❌ 运行失败: {e}")

if __name__ == "__main__":
    main()
