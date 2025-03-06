import logging
import os
import asyncio
import time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
import datetime
import re
from collections import Counter

# Tải biến môi trường từ file .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Cấu hình logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Định nghĩa nguồn tin tức
NEWS_SOURCES = {
    "vnexpress": {
        "url": "https://vnexpress.net/suc-khoe",
        "article_selector": "article.item-news",
        "title_selector": "h3.title-news a"
    },
    "dantri": {
        "url": "https://dantri.com.vn/suc-khoe.htm",
        "article_selector": "article.article-item",
        "title_selector": "h3.article-title a"
    },
    "thanhnien": {
        "url": "https://thanhnien.vn/suc-khoe.htm",
        "article_selector": "div.relative",
        "title_selector": "h3.title a"
    },
    "nld": {
        "url": "https://nld.com.vn/suc-khoe.htm",
        "article_selector": "div.item-news",
        "title_selector": "h3.title-news a"
    },
    "suckhoedoisong": {
        "url": "https://suckhoedoisong.vn",
        "article_selector": "article.item-news",
        "title_selector": "h3.title-news a"
    },
    "tuoitre": {
        "url": "https://tuoitre.vn/suc-khoe.htm",
        "article_selector": "div.news-item",
        "title_selector": "h3.title a"
    },
    "znews": {
        "url": "https://lifestyle.znews.vn/suc-khoe.html",
        "article_selector": "article.article-item",
        "title_selector": "h3.article-title a"
    },
    "vietnamnet": {
        "url": "https://vietnamnet.vn/suc-khoe",
        "article_selector": "div.item-news",
        "title_selector": "h3.title a"
    },
    "doisongphapluat": {
        "url": "https://doisongphapluat.com.vn/y-te-167.html",
        "article_selector": "div.news-item",
        "title_selector": "h3.title a"
    }
}

# Định nghĩa từ khóa ghép và từ khóa y tế quan trọng
COMPOUND_KEYWORDS = {
    'bệnh nền', 'cúm a', 'covid-19', 'sốt xuất huyết', 'tiểu đường', 'huyết áp cao',
    'ung thư phổi', 'viêm gan', 'đau đầu', 'rối loạn', 'tâm thần', 'tim mạch',
    'xương khớp', 'da liễu', 'răng miệng', 'tai mũi họng', 'hô hấp', 'tiêu hóa',
    'thần kinh', 'nội tiết', 'dinh dưỡng', 'y tế', 'sức khỏe', 'điều trị',
    'phòng bệnh', 'thuốc men', 'vaccine', 'tiêm chủng', 'xét nghiệm',
    'chăm sóc', 'phẫu thuật', 'cấp cứu', 'nhiễm khuẩn', 'kháng sinh',
    'dị ứng', 'trầm cảm', 'mãn tính', 'biến chứng', 'ngộ độc'
}

HEALTH_KEYWORDS = {
    'sức khỏe', 'bệnh', 'thuốc', 'điều trị', 'triệu chứng', 'virus',
    'vaccine', 'tiêm chủng', 'ung thư', 'tim mạch', 'huyết áp',
    'sốt', 'viêm', 'nhiễm', 'dịch', 'xét nghiệm',
    'thai kỳ', 'sinh lý', 'dinh dưỡng', 'vitamin', 'tập luyện',
    'covid', 'dịch bệnh', 'thực phẩm', 'béo phì',
    'tiểu đường', 'hô hấp', 'da liễu', 'răng miệng', 'thần kinh',
    'tâm lý', 'stress', 'tử vong', 'khám bệnh', 'phòng bệnh',
    'y tế', 'bác sĩ', 'bệnh viện', 'phòng khám', 'cấp cứu',
    'thuốc', 'điều dưỡng', 'chăm sóc', 'phẫu thuật', 'xương khớp'
}

class NewsBot:
    def __init__(self):
        self.cached_news = []
        self.last_update = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý lệnh /start"""
        welcome_message = """
        👋 Xin chào! Tôi là bot tìm kiếm tin tức sức khỏe 🏥
        
        Các lệnh có sẵn:
        /news - Lấy tin tức mới nhất
        /keywords - Xem các từ khóa hot
        /help - Hiển thị trợ giúp
        """
        await update.message.reply_text(welcome_message)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý lệnh /help"""
        help_text = """
        🤖 Các lệnh có sẵn:
        
        /news - Lấy tin tức mới nhất từ các báo uy tín
        /keywords - Xem các từ khóa hot về sức khỏe
        /help - Hiển thị trợ giúp này
        
        📝 Chú ý:
        - Tin tức được cập nhật mỗi 24 giờ
        - Từ khóa được phân tích từ các tin tức mới nhất
        """
        await update.message.reply_text(help_text)

    def crawl_single_source(self, source_name, source_info):
        """Crawl tin tức từ một nguồn cụ thể với xử lý lỗi chi tiết"""
        try:
            response = requests.get(source_info['url'], headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.select(source_info['article_selector'])
            
            if not articles:
                logger.warning(f"Không tìm thấy bài viết nào từ {source_name} với selector: {source_info['article_selector']}")
                return []
            
            news_items = []
            for article in articles[:5]:  # Lấy 5 bài mới nhất
                title_element = article.select_one(source_info['title_selector'])
                if title_element and title_element.text:
                    title = title_element.text.strip()
                    title = re.sub(r'\s+', ' ', title)
                    
                    # Thêm URL của bài viết nếu có
                    url = ""
                    if title_element.has_attr('href'):
                        url = title_element['href']
                        # Xử lý URL tương đối
                        if url.startswith('/'):
                            base_url = '/'.join(source_info['url'].split('/')[:3])
                            url = base_url + url
                    
                    news_items.append({
                        'title': title,
                        'source': source_name,
                        'url': url,
                        'timestamp': datetime.datetime.now()
                    })
            
            logger.info(f"Đã crawl thành công {len(news_items)} bài từ {source_name}")
            return news_items
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Lỗi kết nối khi crawl từ {source_name}: {str(e)}")
        except Exception as e:
            logger.error(f"Lỗi không xác định khi crawl từ {source_name}: {str(e)}")
        return []

    def crawl_news(self):
        """Crawl tin tức từ tất cả các nguồn"""
        all_news = []
        for source_name, source_info in NEWS_SOURCES.items():
            source_news = self.crawl_single_source(source_name, source_info)
            all_news.extend(source_news)
            time.sleep(1)  # Delay giữa các request
        
        source_counts = Counter(news['source'] for news in all_news)
        logger.info(f"Tổng số tin tức đã crawl: {len(all_news)}")
        logger.info(f"Phân bố theo nguồn: {dict(source_counts)}")
        
        return all_news

    def get_keywords(self, texts):
        """Trích xuất từ khóa với cách xử lý văn bản cải tiến"""
        try:
            # Từ dừng tiếng Việt
            vietnamese_stop_words = set([
                'và', 'của', 'có', 'được', 'trong', 'đã', 'với', 'các', 'những',
                'để', 'là', 'một', 'không', 'này', 'cho', 'khi', 'đến', 'về',
                'như', 'từ', 'người', 'ra', 'sẽ', 'cần', 'phải', 'tại', 'trong',
                'theo', 'được', 'nhưng', 'vì', 'do', 'đang', 'sẽ', 'nên', 'còn',
                'thế', 'nào', 'gì', 'bị', 'sau', 'về', 'làm', 'mới', 'ai',
                'biết', 'nếu', 'thì', 'đây', 'khi', 'rất', 'lúc', 'vừa', 'đề',
                'năm', 'qua', 'hay', 'trên', 'dưới', 'tới', 'đều', 'việc'
            ])

            keyword_counts = Counter()

            # Bước 1: Trích xuất từ ghép từ tiêu đề
            for text in texts:
                # Chuẩn hóa text
                text = text.lower()
                text = re.sub(r'[.,!?:]', ' ', text)
                
                # Tìm từ ghép đầu tiên
                for compound_keyword in COMPOUND_KEYWORDS:
                    if compound_keyword in text:
                        keyword_counts[compound_keyword] += 1
            
            # Bước 2: Xử lý lại tiêu đề để tìm từ khóa đơn và cặp từ
            for text in texts:
                # Chuẩn hóa text
                text = text.lower()
                text = re.sub(r'[.,!?:]', ' ', text)
                
                # Tách câu thành từ
                words = text.split()
                
                # Xử lý từng từ đơn trong HEALTH_KEYWORDS
                for word in words:
                    if word in HEALTH_KEYWORDS and word not in vietnamese_stop_words:
                        keyword_counts[word] += 1
                
                # Xử lý từng cặp từ liên tiếp
                for i in range(len(words) - 1):
                    bigram = ' '.join(words[i:i+2])
                    # Kiểm tra bigram có chứa từ khóa sức khỏe không
                    if any(keyword in bigram for keyword in HEALTH_KEYWORDS):
                        if not any(word in vietnamese_stop_words for word in words[i:i+2]):
                            keyword_counts[bigram] += 1
                
                # Xử lý từng bộ ba từ liên tiếp
                for i in range(len(words) - 2):
                    trigram = ' '.join(words[i:i+3])
                    # Kiểm tra trigram có chứa từ khóa sức khỏe không
                    if any(keyword in trigram for keyword in HEALTH_KEYWORDS):
                        if not all(word in vietnamese_stop_words for word in words[i:i+3]):
                            keyword_counts[trigram] += 1

            # Lọc kết quả: chấp nhận từ khóa xuất hiện ít nhất 1 lần và loại bỏ từ quá ngắn
            valid_keywords = [(k, v) for k, v in keyword_counts.items() if len(k) > 1]
            
            # Ưu tiên từ khóa theo tần suất xuất hiện và độ dài
            sorted_keywords = sorted(valid_keywords, 
                                  key=lambda x: (x[1], len(x[0].split())), 
                                  reverse=True)
            
            logger.info(f"Số lượng từ khóa tìm được: {len(sorted_keywords)}")
            logger.info(f"Các từ khóa: {sorted_keywords[:10]}")
            
            return sorted_keywords[:10]  # Trả về 10 từ khóa hàng đầu

        except Exception as e:
            logger.error(f"Lỗi khi trích xuất từ khóa: {str(e)}")
            logger.exception(e)
            return []

    async def get_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý lệnh /news - Hiển thị các bài báo đã crawl"""
        try:
            await update.message.reply_text("🔍 Đang tìm kiếm tin tức sức khỏe mới...")
            
            current_time = datetime.datetime.now()
            if not self.last_update or (current_time - self.last_update).seconds > 86400:
                self.cached_news = self.crawl_news()
                self.last_update = current_time
            
            if not self.cached_news:
                await update.message.reply_text("❌ Không tìm thấy tin tức nào. Vui lòng thử lại sau.")
                return
            
            # Phân loại tin tức theo nguồn
            news_by_source = {}
            for news in self.cached_news:
                source = news['source']
                if source not in news_by_source:
                    news_by_source[source] = []
                news_by_source[source].append(news)
            
            # Tạo message hiển thị tin tức
            message = "📰 TIN TỨC SỨC KHỎE MỚI NHẤT\n\n"
            
            # Thêm tin tức từ mỗi nguồn vào message
            for source, news_list in news_by_source.items():
                message += f"🔹 {source.upper()}:\n"
                for idx, news in enumerate(news_list[:5], 1):  # Hiển thị tối đa 5 tin từ mỗi nguồn
                    title = news['title']
                    url = news['url'] if 'url' in news and news['url'] else "Không có URL"
                    message += f"  {idx}. {title}\n"
                    if url != "Không có URL":
                        message += f"     👉 {url}\n"
                message += "\n"
            
            # Thêm thời gian cập nhật
            message += f"⏰ Cập nhật: {self.last_update.strftime('%d/%m/%Y %H:%M')}"
            
            await update.message.reply_text(message)
        except Exception as e:
            logger.error(f"Lỗi khi lấy tin tức: {str(e)}")
            logger.exception(e)
            await update.message.reply_text("❌ Có lỗi xảy ra. Vui lòng thử lại sau.")

    async def get_keywords_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý lệnh /keywords"""
        try:
            await update.message.reply_text("🔍 Đang phân tích từ khóa sức khỏe nổi bật...")
            
            current_time = datetime.datetime.now()
            if not self.last_update or (current_time - self.last_update).seconds > 86400:
                self.cached_news = self.crawl_news()
                self.last_update = current_time
            
            if not self.cached_news:
                await update.message.reply_text("❌ Không tìm thấy tin tức nào. Vui lòng thử lại sau.")
                return
            
            titles = [news['title'] for news in self.cached_news]
            keywords = self.get_keywords(titles)
            
            if not keywords:
                await update.message.reply_text("❌ Không tìm thấy từ khóa phù hợp. Vui lòng thử lại sau.")
                return
            
            response = "🔥 Các từ khóa nổi bật về sức khỏe:\n\n"
            for word, count in keywords:
                # Thêm emoji phù hợp cho từng loại từ khóa
                emoji = "🏥" if word in COMPOUND_KEYWORDS else "📊"
                response += f"{emoji} {word}: {count} lần\n"
            
            # Thêm chú thích
            response += "\n💡 Chú thích:\n"
            response += "🏥 - Từ khóa y tế quan trọng\n"
            response += "📊 - Từ khóa phổ biến khác"
            
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Lỗi khi lấy từ khóa: {str(e)}")
            await update.message.reply_text("❌ Có lỗi xảy ra. Vui lòng thử lại sau.")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Xử lý lỗi chung cho bot"""
        logger.error(f"Lỗi khi xử lý update {update}: {context.error}")
        try:
            if update and update.message:
                await update.message.reply_text(
                    "❌ Có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại sau hoặc liên hệ admin."
                )
        except Exception as e:
            logger.error(f"Lỗi khi gửi thông báo lỗi: {e}")

def main():
    """Khởi động bot"""
    try:
        # Khởi tạo ứng dụng với token
        application = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Khởi tạo bot
        bot = NewsBot()

        # Thêm các handler xử lý lệnh
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("help", bot.help))
        application.add_handler(CommandHandler("news", bot.get_news))
        application.add_handler(CommandHandler("keywords", bot.get_keywords_command))
        
        # Thêm error handler
        application.add_error_handler(bot.error_handler)

        # Log khi bot khởi động
        logger.info("Bot đã sẵn sàng và bắt đầu polling...")
        
        # Chạy bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Lỗi khởi động bot: {str(e)}")
        raise

if __name__ == "__main__":
    main()