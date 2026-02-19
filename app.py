import streamlit as st
import google.generativeai as genai
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

st.set_page_config(page_title="受験生向け 英文和訳添削", layout="wide")

st.markdown("""
<style>
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-color: rgba(255, 255, 255, 0.95);
        z-index: 99999;
        display: flex;
        flex-direction: column;
        justify_content: center;
        align-items: center;
        text-align: center;
        padding: 20px;
    }
    .trivia-box {
        max-width: 600px;
        padding: 2rem;
        border-radius: 15px;
        background: #f8f9fa;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        border: 2px solid #e9ecef;
    }
    .trivia-title {
        font-size: 1.5rem;
        color: #ff4b4b;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .trivia-content {
        font-size: 1.8rem;
        color: #333;
        font-weight: bold;
        line-height: 1.6;
    }
    .loading-spinner {
        margin-top: 2rem;
        font-size: 1.2rem;
        color: #666;
    }
    @media (max-width: 600px) {
        .trivia-content {
            font-size: 1.4rem;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("受験生向け 英文和訳添削システム")

TRIVIA_LIST = [
    "💡 無生物主語の訳し方：直訳すると不自然な時は、主語を「～によって・～のせいで」と副詞的に訳し、目的語を主語にして訳すと綺麗になります！",
    "💡 名詞構文の訳し方：名詞を動詞のように、所有格や目的格を主語や目的語のように「訳し下す」と自然な日本語に。",
    "💡 関係代名詞の継続用法（, which など）は、後ろから訳し上げず、前から「そしてそれは～」と順に訳すのがコツ！",
    "💡 英語の受動態は、日本語では能動態に直して訳した方が自然になることが多いです。",
    "💡 代名詞（it, they, themなど）は、文脈が許す限り具体的な名詞で補って訳すと分かりやすい和訳になります。",
    "💡 'not always' は「いつも～ない」ではなく「いつも～とは限らない」（部分否定）！",
    "💡 'few' と 'a few' の違いに注意！ 'a' がないと「ほとんど～ない」という否定的な意味になります。",
    "💡 'hardly' や 'scarcely' はそれだけで「ほとんど～ない」という否定語。notとセットにしないように！",
    "💡 'manage to do' は「どうにかして～する」。ただ「～した」と訳すより、努力したニュアンスを入れよう。",
    "💡 'fail to do' は「～しそこなう、～できない」。失敗した、と直訳すると文脈に合わないことが多いです。",
    "💡 'too ～ to ...' 構文は「～すぎて…できない」または「…するには～すぎる」。文脈に合わせて自然な方を選ぼう。",
    "💡 比較級を用いた 'no more ～ than ...' は「…でないのと同様に～でない」（クジラの構文）。両方否定です！",
    "💡 'It is ~ that ...' の強調構文は、「…なのは～だ」と、強調されている部分を際立たせて訳すのがポイント。",
    "🧠 エビングハウスの忘却曲線：人間は1日経つと74%忘れる。復習は「今日中」にやるのが最強。",
    "🧠 ポモドーロ・テクニック：25分勉強＋5分休憩が、人間の集中力の限界に最適。"
]

try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except FileNotFoundError:
    st.error("設定ファイル (.streamlit/secrets.toml) が見つかりません。")
    st.stop()
except KeyError:
    st.error("Secretsに 'GOOGLE_API_KEY' が設定されていません。")
    st.stop()

with st.sidebar:
    st.header("⚙️ システム設定")
    
    st.subheader("しろねこ選択")
    model_choice = st.radio(
        "使用するモデルを選んでください",
        ["はいぱーしろねこ", "のーまるしろねこ"],
        index=0
    )
    
    model_map = {
        "はいぱーしろねこ": "models/gemini-2.5-pro",
        "のーまるしろねこ": "models/gemini-2.0-flash"
    }
    selected_model_name = model_map[model_choice]

    st.divider()
    
    st.subheader("📝 採点設定")
    difficulty = st.select_slider(
        "採点基準の厳しさ",
        options=["やさしめ", "ちゅうくらい", "厳しめ"],
        value="ちゅうくらい"
    )
    max_score = st.number_input("この問題の配点", min_value=10, max_value=200, value=30, step=10)


def get_gemini_response_sync(prompt, model_name):
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return response.text
    except Exception as e:
        return f"ERROR: {e}"

def image_to_text(image, model_name):
    try:
        model = genai.GenerativeModel(model_name)
        prompt = "この画像に書かれている文字をすべて読み取って、テキストとして出力してください。"
        response = model.generate_content([prompt, image])
        return response.text.strip()
    except Exception as e:
        st.error(f"画像読み取りエラー: {e}")
        return ""

def generate_grading_prompt(problem_text, student_text, difficulty, max_score):
    strictness_instruction = ""
    if difficulty == "やさしめ":
        strictness_instruction = "受験生を励ますために、致命的な誤読以外は柔軟に解釈し、良い点を積極的に評価してください。"
    elif difficulty == "ちゅうくらい":
        strictness_instruction = "標準的な大学入試の基準で、減点法に基づき客観的に採点してください。"
    elif difficulty == "厳しめ":
        strictness_instruction = "難関大学レベルの非常に厳しい基準で、細かなニュアンスのズレや時制のミスも容赦なく減点してください。"

    prompt = f"""
    あなたはプロの英語教師です。以下の「英語の問題文」に対する「生徒の和訳（日本語解答）」を採点・添削してください。
    【重要】出力は純粋なJSONデータのみにしてください。

    【設定】
    - 配点: 全体で {max_score} 点満点
    - 難易度設定: {difficulty} ({strictness_instruction})

    【問題文 (英語)】
    {problem_text}

    【生徒の解答 (日本語)】
    {student_text}

    【採点基準】
    配点比率は「構文把握・意味理解」が全体の約83%、「日本語表現」が約17%となるように換算してください。
    （例：30点満点なら、構文25点 / 表現5点 の比率）

    1. 構文把握・意味理解 (スコア比重: 大)
       - 文法的に与えられた英文を数個に分割し、文法的重要度や解釈の難度、含まれる単語の難度に比例して減点法で採点すること。
       - S、V、O、C、Mについて正確に捉えているか。
       - 関係詞・節の構造を正確に捉えているか。
       - 構文を正しく理解し、重要文法事項（Too～to…や、仮定法、強調など）を反映させた訳になっているか。
       - 決まり文句のような訳を正確に日本語に反映させているか。
       - 無生物主語を正しく訳出できているか。
       - 修飾関係が正しいか。
       - 時制が正しいか。
       - 単語の意味を間違えていないか。

    2. 日本語表現 (スコア比重: 小)
       - 不自然でない日本語か。語順・主述関係が破綻していないか。
       - 日本語表現に関して誤解を生む場合は各所につき減点（目安として1箇所1割程度の減点）。
       - 表現の細やかな差異については「補足」として扱い、減点せずにアドバイスを行うこと。

    【出力JSONキー構成】
    {{
        "total_score": 整数 ({max_score}点以下の合計点),
        "breakdown": {{
            "syntax_score": 整数 (構文把握・意味理解の点数),
            "expression_score": 整数 (日本語表現の点数)
        }},
        "corrected_sentence": "修正後の自然な和訳",
        "correction_html": "HTML差分文字列 (生徒の解答をベースに、誤訳を <span style='color:red; text-decoration:line-through'>削除</span> <span style='color:green; font-weight:bold'>修正・追加</span> で表現)",
        "feedback": "全体の講評および、減点対象外の表現の細かな差異に関する補足アドバイス",
        "improvement_points": ["改善点リスト（構文ミスや誤読ポイントを具体的に）"],
        "model_answer": "模範解答"
    }}
    """
    return prompt


col1, col2 = st.columns(2)

with col1:
    st.subheader("📝 問題文 (英語)")
    input_method_prob = st.radio("入力方法", ["テキスト", "カメラ/画像"], key="prob_radio", horizontal=True)
    
    problem_text = ""
    if input_method_prob == "テキスト":
        problem_text = st.text_area("問題文を入力", height=150, placeholder="例：It is often said that...")
    else:
        uploaded_prob = st.file_uploader("問題画像をアップロード", type=["jpg", "png"], key="prob_img")
        if uploaded_prob:
            image = Image.open(uploaded_prob)
            st.image(image, caption="画像を確認", use_container_width=True)
            if st.button("文字を読み取る", key="ocr_prob"):
                with st.spinner(f"読み取り中..."):
                    extracted = image_to_text(image, selected_model_name)
                    st.session_state["ocr_prob_text"] = extracted
        problem_text = st.text_area("読み取ったテキスト", value=st.session_state.get("ocr_prob_text", ""), height=150)

with col2:
    st.subheader("✍️ 生徒の和訳解答")
    input_method_ans = st.radio("入力方法", ["テキスト", "カメラ/画像"], key="ans_radio", horizontal=True)
    
    student_text = ""
    if input_method_ans == "テキスト":
        student_text = st.text_area("解答を入力", height=150, placeholder="例：よく言われていることは...")
    else:
        uploaded_ans = st.file_uploader("解答画像をアップロード", type=["jpg", "png"], key="ans_img")
        if uploaded_ans:
            image = Image.open(uploaded_ans)
            st.image(image, caption="画像を確認", use_container_width=True)
            if st.button("文字を読み取る", key="ocr_ans"):
                with st.spinner(f"読み取り中..."):
                    extracted = image_to_text(image, selected_model_name)
                    st.session_state["ocr_ans_text"] = extracted
        student_text = st.text_area("読み取ったテキスト", value=st.session_state.get("ocr_ans_text", ""), height=150)

st.divider()

if st.button(f"💯 採点スタート ({model_choice})", type="primary", use_container_width=True):
    if not problem_text or not student_text:
        st.warning("問題文と解答の両方を入力してください。")
    else:
        prompt = generate_grading_prompt(problem_text, student_text, difficulty, max_score)
        
        overlay_placeholder = st.empty()
        executor = ThreadPoolExecutor()
        future = executor.submit(get_gemini_response_sync, prompt, selected_model_name)
        
        start_time = time.time()
        last_switch_time = 0
        current_trivia = random.choice(TRIVIA_LIST)
        
        while not future.done():
            current_time = time.time()
            elapsed = current_time - start_time
            
            if current_time - last_switch_time > 10:
                current_trivia = random.choice(TRIVIA_LIST)
                last_switch_time = current_time
            
            html_content = f"""
            <div class="loading-overlay">
                <div class="trivia-box">
                    <div class="trivia-title">しろねこ先生の豆知識タイム</div>
                    <div class="trivia-content">{current_trivia}</div>
                </div>
                <div class="loading-spinner">
                    <br>採点中... {int(elapsed)}秒経過<br>
                    {model_choice} が添削中...
                </div>
            </div>
            """
            overlay_placeholder.markdown(html_content, unsafe_allow_html=True)
            time.sleep(0.1)
        
        result_json_str = future.result()
        overlay_placeholder.empty()

        if result_json_str and not result_json_str.startswith("ERROR"):
            try:
                json_str = result_json_str.strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                
                data = json.loads(json_str)

                st.success("採点完了！")
                
                score_col1, score_col2 = st.columns([1, 2])
                with score_col1:
                    st.metric(label="獲得スコア", value=f"{data['total_score']} / {max_score}")
                
                with score_col2:
                    bd = data['breakdown']
                    st.write("📊 **項目別評価**")
                    
                    syntax_max = round(max_score * (25 / 30))
                    expression_max = max_score - syntax_max
                    
                    safe_syntax = min(bd['syntax_score'], syntax_max)
                    safe_expr = min(bd['expression_score'], expression_max)
                    
                    st.progress(safe_syntax / syntax_max if syntax_max > 0 else 0, text=f"構文把握・意味理解: {bd['syntax_score']} / {syntax_max}")
                    st.progress(safe_expr / expression_max if expression_max > 0 else 0, text=f"日本語表現: {bd['expression_score']} / {expression_max}")

                st.divider()

                st.subheader("🔍 添削結果")
                st.markdown(f"<div style='font-size:18px; line-height:1.6; padding:15px; background-color:#f0f2f6; border-radius:10px;'>{data['correction_html']}</div>", unsafe_allow_html=True)
                st.caption("赤字取り消し線：誤訳 / 緑字太字：正しい訳への修正・追加")

                st.subheader("しろねこアドバイス")
                st.info(data['feedback'])
                
                with st.expander("詳細な改善ポイントを見る", expanded=True):
                    for point in data['improvement_points']:
                        st.write(f"- {point}")

                st.subheader("✨ 模範解答例")
                st.code(data['model_answer'], language='text')

            except json.JSONDecodeError:
                st.error("データの解析に失敗しました。")
                st.text(result_json_str)
        else:
            st.error(f"エラーが発生しました: {result_json_str}")
