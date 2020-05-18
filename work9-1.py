from flask import Flask, render_template, request, session, redirect
from bs4 import BeautifulSoup as BS
import requests
import re
import os
import pymysql
from selenium import webdriver
from konlpy.tag import Kkma
import base64

if __name__ == "__main__":
    # Flask 실행 환경 설정
    app = Flask(__name__,
                template_folder="./template",
                static_folder="./static")
    app.env = "development"
    app.debug = True
    app.secret_key = "sldkjfsld"

    # Selenium Web Driver 설정
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome("./chromedriver", options=options)

    # 한글 형태소 분석 엔진 설정
    kkma = Kkma()

    # MySQL 클라이언트 설정
    db = pymysql.connect(
        user="root",
        passwd="new123",
        db="web",
        host="localhost",
        charset="utf8",
        cursorclass=pymysql.cursors.DictCursor,
    )

    @app.route("/")
    def index():
        # 사용자 로그인 확인
        is_logged_in = True if session.get("user") else False

        if is_logged_in:
            return render_template(
                "index.html",
                is_logged_in=is_logged_in,
                user=session.get("user").get("name"),
            )

        return render_template("index.html", is_logged_in=is_logged_in)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")

        # 로그인 요청 시 DB에서 사용자 정보 확인
        cursor = db.cursor()
        cursor.execute(f"""
            SELECT id, name, profile FROM author
            WHERE name = '{ request.form['userid'] }' AND
                password = SHA2('{ request.form['password'] }', 256)
        """)

        # 로그인 성공
        user = cursor.fetchone()
        if user:
            # 세션 정보 저장
            session["user"] = user
            return redirect("/")

        # 로그인 실패
        return render_template("login.html", msg="로그인정보를 확인 요망.")

    @app.route("/logout")
    def logout():
        # 세션 정보 삭제
        session.pop("user")

        return redirect("/")

    @app.route("/join", methods=["GET", "POST"])
    def join():
        if request.method == "GET":
            return render_template("join.html")

        # 사용자 정보 입력
        userid = request.form.get("userid")
        password = request.form.get("password")
        profile = request.form.get("profile")

        # 중복 검사
        cursor = db.cursor()
        cursor.execute(f"""SELECT id FROM author WHERE name = '{ userid }'""")
        res = cursor.fetchone()
        if res:
            return render_template("join.html", msg="ID 중복입니다. 다시 가입하세요.")

        # 신규 등록
        query = f"""INSERT INTO `author` VALUES (id, '{ userid }', '{ profile }', SHA2('{ password }', 256));"""
        cursor = db.cursor()
        cursor.execute(query)
        db.commit()

        # 메인 페이지로 이동
        return redirect("/")

    @app.route("/withdrawal", methods=["GET", "POST"])
    def withdrawal():
        if request.method == "GET":
            return render_template("withdrawal.html")

        # 탈퇴할 사용자 정보
        userid = session.get("user").get("name")
        password = request.form.get("password")

        # ID, 비밀번호 검사
        cursor = db.cursor()
        cursor.execute(f"""
            SELECT id FROM author
            WHERE name = '{ userid }' AND password = SHA2('{ password }', 256)
        """)

        # 사용자 삭제
        user = cursor.fetchone()
        if user:
            query = f"""DELETE FROM author WHERE name = '{ userid }'"""
            cursor = db.cursor()
            cursor.execute(query)
            db.commit()

            # 세션 정보 삭제
            session.pop("user")

            # 메인 페이지로 이동
            return redirect("/")

        # 사용자 삭제 실패
        return render_template("withdrawal.html", msg="비밀번호를 다시 입력하세요.")

    @app.route("/news/ranking", methods=["GET", "POST"])
    def news_ranking():
        if request.method == "GET":
            return render_template("news_ranking.html")

        url = f"https://media.daum.net/ranking/?regDate={ request.form.get('date') }"
        driver.get(url)

        soup = BS(driver.page_source, "html.parser")

        news_links = [
            (tag.get("href"), tag.get_text())
            for tag in soup.select(".rank_news strong.tit_thumb a.link_txt")
        ]

        return render_template("news_ranking.html", msg=news_links)

    @app.route("/news/words")
    def news_words():
        url = request.args.get("url")
        if url is None:
            return render_template("news_words.html", msg="뉴스 랭킹 페이지에서 접근하세요.")
            # return redirect("/news/ranking")
            # return redirect("/")

        driver.get(url)

        soup = BS(driver.page_source, "html.parser")

        content = soup.select(".article_view")[0].get_text()

        # Konply pos : 품사 분석
        words = kkma.pos(content)

        # 일반명사: NNG, 고유명사 : NNP
        words = [word for word, tag in words if tag == "NNG" or tag == "NNP"]
        words = [
            dict(word=word, count=words.count(word)) for word in set(words)
        ]

        words = sorted(words, key=lambda x: x.get("count"), reverse=True)

        return render_template("news_words.html", words=words)

    @app.route("/downloads/<keyword>")
    def downloads(keyword):
        url = f"https://www.google.com/search?q={keyword}&tbm=isch"
        driver.get(url)
        soup = BS(driver.page_source, "html.parser")

        try:
            for root, _, files in os.walk(f"static/download/{keyword}", topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
        except:
            pass
        os.makedirs(f"static/download/{keyword}", exist_ok=True)

        img_list = []
        # 이미지 파일(src)과 URL link(data-src)
        img_links = [(tag.get("src"), tag.get("data-src"))
                     for tag in soup.select(".rg_i")]
        for i, (img_data, img_link) in enumerate(img_links):
            ext = "jpg"
            if img_data:
                data = base64.b64decode(img_data.split(",")[1])

                # 이미지 파일 확장자 확인
                regex = re.compile("^data:image/([^;]+)")
                ext = regex.findall(img_data)[0]
            elif img_link:
                res = requests.get(img_link)

                # 이미지 파일 확장자 확인
                data = res.content

                regex = re.compile("^image/(.+)")
                ext = regex.findall(res.headers.get("Content-Type"))[0]
            else:
                continue

            # Data -> File, Link대신에 이미지 파일을 직접 화면에 출력하는 작업
            filepath = f"static/download/{keyword}/{i}.{ext}"
            img_list.append(f"/{filepath}")
            with open(f"./{filepath}", "wb") as f:
                f.write(data)

        return render_template("downloads.html", img_link=img_list)

    app.run(port=5005)

    exit(0)
