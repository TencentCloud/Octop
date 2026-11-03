const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const xlsx = require('xlsx');
const https = require('https');
const http = require('http');

/**
 * 淘宝产品调研工具
 * 
 * 使用方法:
 * node taobao_research.js <关键词> <价格区间> <数量> [输出目录]
 * 
 * 示例:
 * node taobao_research.js "AI机器人" "0-169" 15
 * node taobao_research.js "智能手表" "100-500" 20 ./output
 */

class TaobaoResearcher {
    constructor(options = {}) {
        this.keyword = options.keyword || 'AI机器人';
        this.priceMin = options.priceMin || 0;
        this.priceMax = options.priceMax || 1000;
        this.maxItems = options.maxItems || 10;
        this.outputDir = options.outputDir || path.join(__dirname, '..', '..', 'taobao_research');
        this.userDataDir = path.join(this.outputDir, 'browser_data');
        
        // 确保目录存在
        if (!fs.existsSync(this.outputDir)) fs.mkdirSync(this.outputDir, { recursive: true });
        if (!fs.existsSync(this.userDataDir)) fs.mkdirSync(this.userDataDir, { recursive: true });
    }

    async init() {
        console.log('🌐 启动浏览器...');
        this.context = await chromium.launchPersistentContext(this.userDataDir, {
            headless: false,
            slowMo: 200,
            viewport: { width: 1920, height: 1080 }
        });
        this.page = this.context.pages()[0] || await this.context.newPage();
        
        // 检查登录状态
        await this.page.goto('https://s.taobao.com', { waitUntil: 'domcontentloaded', timeout: 30000 });
        await this.page.waitForTimeout(3000);
        
        const needLogin = await this.page.locator('.login-box, #login-form').count() > 0;
        if (needLogin) {
            console.log('⚠️  需要登录淘宝，请在浏览器中完成登录后按回车继续...');
            await new Promise(r => {
                const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout });
                rl.question('', () => { rl.close(); r(); });
            });
        }
        console.log('✅ 浏览器准备就绪');
    }

    async getProductReviews(productUrl) {
        try {
            const itemId = productUrl.match(/id=(\d+)/)?.[1];
            if (!itemId) return '';
            
            const newPage = await this.context.newPage();
            await newPage.goto(productUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
            await newPage.waitForTimeout(5000);
            
            const reviews = await newPage.evaluate(() => {
                const bodyText = document.body.innerText;
                
                // 模式: 386人评价 / 1000+人评价
                let match = bodyText.match(/(\d+[\d万+]*人评价)/);
                if (match) return match[1];
                
                // 找包含"人评价"的元素
                const elements = Array.from(document.querySelectorAll('*'));
                for (const el of elements) {
                    const text = el.textContent.trim();
                    if (text.includes('人评价') && text.length < 30) {
                        return text;
                    }
                }
                
                // 累计评价格式
                match = bodyText.match(/累计评价[\s:：]*(\d+[\d万+]*)/);
                if (match) return `${match[1]}人评价`;
                
                return '';
            });
            
            await newPage.close();
            return reviews;
        } catch (e) {
            console.log(`  ⚠️  获取评价数失败: ${e.message}`);
            return '';
        }
    }

    async searchAndExtract() {
        console.log(`\n🔍 搜索: ${this.keyword} | 价格: ${this.priceMin}-${this.priceMax} | 数量: ${this.maxItems}`);
        
        let url = `https://s.taobao.com/search?q=${encodeURIComponent(this.keyword)}`;
        url += '&sort=sale-desc'; // 按销量排序
        if (this.priceMin !== null && this.priceMax !== null) {
            url += `&filter=reserve_price[${this.priceMin},${this.priceMax}]`;
        }
        
        await this.page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
        console.log('⏳ 等待页面加载...');
        await this.page.waitForTimeout(8000);
        
        // 截图调试
        const debugFile = path.join(this.outputDir, `debug_${this.keyword}_${this.priceMin}_${this.priceMax}.png`);
        await this.page.screenshot({ path: debugFile });
        
        console.log('📦 提取产品数据...');
        const cardCount = await this.page.locator('.doubleCard--gO3Bz6bu').count();
        console.log(`  找到 ${cardCount} 个产品卡片`);
        
        const products = await this.page.evaluate(({max, priceMin, priceMax}) => {
            const results = [];
            const seenIds = new Set();
            const cards = document.querySelectorAll('.doubleCard--gO3Bz6bu');
            
            for (const card of cards) {
                if (results.length >= max) break;
                
                // 提取商品ID
                let itemId = null;
                const childWithId = card.querySelector('[data-item]');
                if (childWithId) {
                    itemId = childWithId.getAttribute('data-item');
                }
                if (!itemId) {
                    const link = card.querySelector('a[href*="item"]');
                    if (link) {
                        const href = link.getAttribute('href');
                        const match = href?.match(/id=(\d+)/);
                        if (match) itemId = match[1];
                    }
                }
                
                if (!itemId || seenIds.has(itemId)) continue;
                
                // 提取标题
                const titleEl = card.querySelector('.title--ASSt27UY, [class*="title"]');
                const title = titleEl?.textContent?.trim() || '';
                
                // 提取价格
                let price = '';
                const priceIntEl = card.querySelector('.priceInt--yqqZMJ5a');
                const priceFloatEl = card.querySelector('.priceFloat--QBXhQJ1w');
                if (priceIntEl) {
                    price = priceIntEl.textContent.trim();
                    if (priceFloatEl) {
                        price += priceFloatEl.textContent.trim();
                    }
                }
                
                // 价格筛选
                const priceNum = parseFloat(price);
                if (!priceNum || (priceMin !== null && priceMax !== null && (priceNum < priceMin || priceNum > priceMax))) {
                    continue;
                }
                
                // 提取销量
                const salesEl = card.querySelector('.realSales--XZJiepmt');
                const sales = salesEl?.textContent?.trim() || '';
                
                // 提取店铺
                const shopEl = card.querySelector('.shopNameText--DmtlsDKm');
                const shop = shopEl?.textContent?.trim() || '';
                
                // 提取图片
                const imgEl = card.querySelector('img');
                const image = imgEl?.src || imgEl?.getAttribute('data-src') || '';
                
                if (title && price) {
                    seenIds.add(itemId);
                    results.push({
                        title,
                        price,
                        sales,
                        shop,
                        image,
                        url: `https://item.taobao.com/item.htm?id=${itemId}`,
                        itemId,
                        reviews: ''
                    });
                }
            }
            
            return results;
        }, {max: this.maxItems, priceMin: this.priceMin, priceMax: this.priceMax});
        
        console.log(`✅ 提取到 ${products.length} 个产品`);
        
        // 获取每个产品的评价数
        console.log('📊 获取评价数...');
        for (let i = 0; i < products.length; i++) {
            const p = products[i];
            console.log(`  [${i+1}/${products.length}] ${p.title?.substring(0, 20)}...`);
            
            p.reviews = await this.getProductReviews(p.url);
            if (p.reviews) {
                console.log(`      评价数: ${p.reviews}`);
            }
            
            if (i < products.length - 1) {
                await this.page.waitForTimeout(4000 + Math.random() * 2000);
            }
        }
        
        // 显示结果预览
        products.forEach((p, i) => {
            console.log(`  [${i+1}] ${p.title?.substring(0, 25)}... ¥${p.price} | 销量:${p.sales || '-'} | 评价:${p.reviews || '-'}`);
        });
        
        return products;
    }

    async downloadImage(url, filepath) {
        return new Promise((resolve, reject) => {
            const protocol = url.startsWith('https') ? https : http;
            const file = fs.createWriteStream(filepath);
            protocol.get(url, (response) => {
                if (response.statusCode !== 200) {
                    reject(new Error(`Failed to download: ${response.statusCode}`));
                    return;
                }
                response.pipe(file);
                file.on('finish', () => {
                    file.close();
                    resolve(filepath);
                });
            }).on('error', reject);
        });
    }

    async saveToExcel(products) {
        if (products.length === 0) {
            console.log('❌ 没有产品数据可保存');
            return null;
        }
        
        const priceRange = `${this.priceMin}-${this.priceMax}`;
        const imageDir = path.join(this.outputDir, 'images', priceRange);
        if (!fs.existsSync(imageDir)) fs.mkdirSync(imageDir, { recursive: true });
        
        console.log('📥 下载图片...');
        for (let i = 0; i < products.length; i++) {
            const p = products[i];
            if (p.image) {
                try {
                    const ext = p.image.match(/\.(jpg|jpeg|png|gif)/i)?.[0] || '.jpg';
                    const imgPath = path.join(imageDir, `img_${i+1}${ext}`);
                    await this.downloadImage(p.image, imgPath);
                    p.localImage = imgPath;
                } catch (e) {
                    console.log(`  ⚠️  图片下载失败 [${i+1}]: ${e.message}`);
                    p.localImage = '';
                }
            }
        }
        
        const data = products.map((p, i) => ({
            '序号': i + 1,
            '主图': '',
            '标题': p.title,
            '价格': p.price,
            '销量': p.sales,
            '评价数': p.reviews,
            '店铺': p.shop,
            '链接': p.url,
            '_imagePath': p.localImage || '',
            '_imageUrl': p.image || ''
        }));

        const ws = xlsx.utils.json_to_sheet(data);
        const wb = xlsx.utils.book_new();
        xlsx.utils.book_append_sheet(wb, ws, '产品列表');
        
        ws['!cols'] = [
            {wch: 8}, {wch: 20}, {wch: 50}, {wch: 12}, 
            {wch: 15}, {wch: 15}, {wch: 25}, {wch: 50}
        ];
        ws['!rows'] = data.map(() => ({ hpt: 80 }));
        
        // 添加超链接
        for (let i = 0; i < data.length; i++) {
            const rowNum = i + 2;
            const cellRef = xlsx.utils.encode_cell({ r: rowNum - 1, c: 7 });
            if (data[i].链接) {
                ws[cellRef] = { t: 's', v: data[i].链接, l: { Target: data[i].链接 } };
            }
        }
        
        // 生成文件名
        const safeKeyword = this.keyword.replace(/[^\w\u4e00-\u9fa5]/g, '_');
        const filename = `taobao_${safeKeyword}_${priceRange}_${Date.now()}.xlsx`;
        const filepath = path.join(this.outputDir, filename);
        xlsx.writeFile(wb, filepath);
        
        // 嵌入图片
        await this.embedImages(filepath, data);
        
        return filepath;
    }
    
    async embedImages(excelPath, data) {
        try {
            const ExcelJS = require('exceljs');
            const workbook = new ExcelJS.Workbook();
            await workbook.xlsx.readFile(excelPath);
            const worksheet = workbook.getWorksheet('产品列表');
            
            for (let i = 0; i < data.length; i++) {
                const rowNum = i + 2;
                const imgPath = data[i]._imagePath;
                
                if (imgPath && fs.existsSync(imgPath)) {
                    try {
                        const imageId = workbook.addImage({
                            filename: imgPath,
                            extension: imgPath.match(/\.(jpg|jpeg|png|gif)$/i)?.[1] || 'jpeg',
                        });

                        worksheet.addImage(imageId, {
                            tl: { col: 1, row: rowNum - 1 },
                            ext: { width: 100, height: 100 }
                        });
                    } catch (e) {
                        console.log(`  ⚠️  嵌入图片失败 [${i+1}]`);
                    }
                }
            }
            
            await workbook.xlsx.writeFile(excelPath);
            console.log('✅ 图片已嵌入Excel');
        } catch (e) {
            console.log('⚠️  图片嵌入失败，使用基础Excel格式');
        }
    }

    async run() {
        await this.init();
        
        const products = await this.searchAndExtract();
        
        let filepath = null;
        if (products.length > 0) {
            filepath = await this.saveToExcel(products);
            console.log(`\n📁 保存: ${filepath}`);
            
            // 显示前5个产品的预览
            console.log('\n📋 产品预览:');
            products.slice(0, 5).forEach((p, idx) => {
                console.log(`  ${idx+1}. ${p.title?.substring(0, 40)}... | ¥${p.price} | ${p.sales || '-'} | ${p.reviews || '-'}`);
            });
        } else {
            console.log('❌ 未找到符合条件的产品');
        }
        
        await this.context.close();
        console.log('\n✅ 完成!');
        
        return {
            keyword: this.keyword,
            priceRange: `${this.priceMin}-${this.priceMax}`,
            count: products.length,
            filepath: filepath,
            products: products.slice(0, 5).map(p => ({
                title: p.title.substring(0, 40) + '...',
                price: p.price,
                sales: p.sales,
                reviews: p.reviews
            }))
        };
    }
}

// 命令行参数解析
function parseArgs() {
    const args = process.argv.slice(2);
    
    if (args.length < 3) {
        console.log('使用方法: node taobao_research.js <关键词> <价格区间> <数量> [输出目录]');
        console.log('示例: node taobao_research.js "AI机器人" "0-169" 15');
        console.log('      node taobao_research.js "智能手表" "100-500" 20 ./output');
        process.exit(1);
    }
    
    const keyword = args[0];
    const priceRange = args[1];
    const maxItems = parseInt(args[2]) || 10;
    const outputDir = args[3] || null;
    
    // 解析价格区间
    const priceMatch = priceRange.match(/(\d+)-(\d+)/);
    if (!priceMatch) {
        console.error('❌ 价格区间格式错误，请使用 "min-max" 格式，如 "0-169"');
        process.exit(1);
    }
    
    return {
        keyword,
        priceMin: parseInt(priceMatch[1]),
        priceMax: parseInt(priceMatch[2]),
        maxItems,
        outputDir
    };
}

// 主程序
if (require.main === module) {
    const options = parseArgs();
    const researcher = new TaobaoResearcher(options);
    
    researcher.run()
        .then(result => {
            console.log('\n📊 最终结果:');
            console.log(JSON.stringify(result, null, 2));
            process.exit(0);
        })
        .catch(err => {
            console.error('❌ 错误:', err);
            process.exit(1);
        });
}

module.exports = { TaobaoResearcher };
