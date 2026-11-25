# -*- coding: utf-8 -*-
"""
TPCN SEO & Policy Compliance Engine v2 (Layer 1 Agent Tool)
- Chu tren video thiet ke DUNG CHUAN nghien cuu tu @baovesuckhoe2424 & @phongbenhthayvichuabenh:
  * Moi dong cuc ngan (3-5 tu, <= 24 ky tu/dong), 3-4 dong/video -> KHONG BAO GIO TRAN KHUNG HINH
  * Bo cuc 3-4 dong: [Trieu chung ngan] / [Ten SP + Xuat xu] / [Cong dung / Lieu dung ngan]
- Caption 3-4 dong + 5 Hashtag chuan SEO + Bo loc tu cam TPCN + Dung Shop GMV Max (isAd: true)
"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = DATA_DIR / "publish_queue.json"

PRODUCT_CATALOG = {
    "canxi_mason": {
        "name": "Canxi hữu cơ Mason Natural Citrate + D3 Mỹ",
        "short_name": "Canxi hữu cơ và D3 Mỹ",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason Natural / Olympian Labs (GMV Max - isAd: TRUE)",
        "product_id": "1731468745270135068",
        "dosage": "Ngày 1 viên/Buổi sáng",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Tê tay, tê chân",
                    "Vọp bẻ, chuột rút",
                    "Canxi hữu cơ và D3 Mỹ",
                    "Ngày 1 viên/Buổi sáng",
                ],
                "symptom": "Tê tay, tê chân, vọp bẻ chuột rút ban đêm, loãng xương",
                "benefit": "Hỗ trợ bổ sung Canxi hữu cơ Citrate + D3 Mỹ dễ hấp thu, ngủ ngon",
                "hashtags": ["#canxihuuco", "#canxid3", "#loangxuong", "#tetaytechan", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Thiếu Canxi ở Nữ",
                    "Nhức lưng, khó ngủ",
                    "Bổ sung Canxi hữu cơ Mỹ",
                    "1 viên/ngày, dùng lâu dài",
                ],
                "symptom": "Dấu hiệu thiếu Canxi đặc biệt ở nữ sau sinh: nhức lưng, khó ngủ",
                "benefit": "Hỗ trợ hấp thu Canxi Citrate + D3 êm dịu dạ dày, không lắng cặn",
                "hashtags": ["#canxi", "#canxihuuco", "#canxid3", "#xuongkhop", "#baovesuckhoe"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Hỗ trợ loãng xương",
                    "Tê tay chân, chuột rút",
                    "Canxi Citrate D3 Mỹ",
                    "Mỗi sáng 1 viên sau ăn",
                ],
                "symptom": "Người trung niên và phụ nữ sau sinh cần bổ sung Canxi mỗi ngày",
                "benefit": "Hỗ trợ duy trì mật độ xương chắc khỏe, vận động dẻo dai",
                "hashtags": ["#canxihuuco", "#bosungcanxi", "#d3", "#loangxuong", "#suckhoechudong"],
            },
        },
    },
    "bokhop_chondro": {
        "name": "Viên uống bổ khớp Chondro-Aid Arkopharma Pháp",
        "short_name": "Bổ khớp Glucosamine Pháp",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505842",
        "dosage": "Ngày 2 viên, sau ăn",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Bổ khớp Pháp",
                    "Bổ sung Glucosamine",
                    "Khô khớp, kêu lụp cụp",
                    "Ngày 2 viên, dùng 3 tháng",
                ],
                "symptom": "Khô khớp, cứng khớp, khớp gối kêu lụp cụp khi vận động",
                "benefit": "Bổ sung Glucosamine Pháp giúp hỗ trợ khớp khỏe và vận động linh hoạt",
                "hashtags": ["#arkopharma", "#chondroaid", "#bokhop", "#glucosamine", "#xuongkhop"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Viên uống Bổ Khớp Pháp",
                    "Hỗ trợ khô khớp, cứng khớp",
                    "Đứng lên ngồi xuống khó",
                    "Sáng 1 viên - Chiều 1 viên",
                ],
                "symptom": "Đứng lên ngồi xuống khó khăn, đau mỏi khớp gối khi đi lại",
                "benefit": "Hỗ trợ dưỡng khớp êm ái, không gây tích nước hay tăng cân",
                "hashtags": ["#bokhop", "#duongkhop", "#chondroaid", "#khopgoi", "#chamsocsuckhoe"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Các vấn đề về Khớp",
                    "Đau mỏi để lâu dễ yếu cơ",
                    "Dùng Bổ Khớp Pháp",
                    "Ngày 2 viên, sau ăn",
                ],
                "symptom": "Nhức mỏi khớp gối, khớp háng để lâu ngại vận động dễ yếu cơ tay chân",
                "benefit": "Hỗ trợ chăm sóc sụn khớp từ Pháp, dùng chung được cho người lớn tuổi",
                "hashtags": ["#chondroaid", "#arkopharma", "#glucosamine", "#daunhucxuongkhop", "#bokhop"],
            },
        },
    },
    "omega3_arko": {
        "name": "Dầu cá Omega 3 Arkopharma Pháp",
        "short_name": "Dầu cá Omega 3 Pháp",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1729632607717722546",
        "dosage": "Ngày 4 viên, sau ăn",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Viên uống Omega 3 Pháp",
                    "Hỗ trợ dưỡng mắt, trí nhớ",
                    "Khô mắt, hay quên",
                    "Ngày 4 viên, dùng lâu dài",
                ],
                "symptom": "Khô mắt, mỏi mắt, hay quên, ngủ không sâu giấc",
                "benefit": "Bổ sung EPA & DHA tinh khiết từ Pháp hỗ trợ thị lực, trí nhớ và tim mạch",
                "hashtags": ["#arkopharma", "#omega3", "#dauca", "#bomat", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Mỡ máu, tim mạch",
                    "Bổ sung Omega 3 Pháp",
                    "Hỗ trợ giấc ngủ ngon",
                    "Ngày 4 viên, sau ăn",
                ],
                "symptom": "Người trung niên cần hỗ trợ mỡ máu, tim mạch và giấc ngủ",
                "benefit": "Dầu cá biển sâu Pháp hỗ trợ tim mạch khỏe mạnh mỗi ngày",
                "hashtags": ["#omega3", "#arkopharma", "#fishoil", "#timmach", "#baovesuckhoe"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Dầu cá Omega 3 Pháp",
                    "Hỗ trợ Tim Mạch & Não Bộ",
                    "Ngày 4 viên, sau ăn",
                ],
                "symptom": "Chăm sóc tim mạch, não bộ và thị lực chủ động mỗi ngày",
                "benefit": "Cung cấp EPA & DHA chuẩn châu Âu hỗ trợ cơ thể khỏe mạnh",
                "hashtags": ["#omega3", "#dauca", "#bonao", "#ngungon", "#arkopharma"],
            },
        },
    },
    "vitamin_azinc": {
        "name": "Vitamin tổng hợp Azinc Arkopharma Pháp",
        "short_name": "Vitamin tổng hợp Pháp",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1729632607717722546",
        "dosage": "2 viên/ngày, mỗi sáng",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Thường xuyên mệt mỏi",
                    "Ăn chay, kén ăn, mới ốm dậy",
                    "Vitamin tổng hợp Pháp",
                    "2 viên/ngày, mỗi sáng",
                ],
                "symptom": "Thường xuyên mệt mỏi, uể oải, ăn chay, kén ăn thiếu vi chất",
                "benefit": "Bổ sung 12 Vitamin & 8 Khoáng chất Pháp hỗ trợ bồi bổ sức khỏe",
                "hashtags": ["#arkopharma", "#vitamintonghop", "#azinc", "#tangdekhang", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Hay ho cảm, ốm vặt",
                    "20 Vitamin khoáng chất",
                    "Tăng đề kháng sức khỏe",
                    "Ngày 2 viên buổi sáng",
                ],
                "symptom": "Hay ốm đau lặt vặt khi đổi mùa, cơ thể suy nhược thiếu chất",
                "benefit": "Hỗ trợ tăng cường sức đề kháng cho người từ 15 tuổi trở lên",
                "hashtags": ["#vitamintonghop", "#multivitamin", "#tangcuongsuckhoe", "#arkopharma", "#vitamin"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Vitamin tổng hợp Pháp",
                    "20 Vitamin & Khoáng chất",
                    "Dùng từ 15 tuổi trở lên",
                    "2 viên/ngày, bồi bổ cơ thể",
                ],
                "symptom": "Sau khi bệnh cần bồi bổ sức khỏe và bổ sung dưỡng chất thiết yếu",
                "benefit": "Cung cấp 20 vitamin khoáng chất đặc biệt nhóm B giảm mệt mỏi",
                "hashtags": ["#arkopharma", "#azinc", "#vitamintonghop", "#multivitamin", "#chamsocsuckhoe"],
            },
        },
    },
    "collagen_chalpha": {
        "name": "Collagen sụn khớp CH-Alpha Plus Đức",
        "short_name": "Collagen sụn khớp Đức",
        "seller_id": "7495319409838361000",
        "seller_name": "Shop CH-Alpha Plus Đức (GMV Max - isAd: TRUE)",
        "product_id": "1729744575343659123",
        "dosage": "Ngày 1 ống buổi sáng",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Collagen sụn khớp Đức",
                    "Hỗ trợ dưỡng khớp, bổ khớp",
                    "Khớp kêu lụp cụp, lắc rắc",
                    "Ngày uống 1 ống buổi sáng",
                ],
                "symptom": "Khô dịch khớp, khớp gối kêu lụp cụp lắc rắc khi vận động",
                "benefit": "Bổ sung Collagen Peptides thủy phân từ Đức hỗ trợ tái tạo sụn khớp",
                "hashtags": ["#chalpha", "#collagensunkhop", "#duongkhop", "#xuongkhop", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Bổ sung Collagen sụn khớp",
                    "Hỗ trợ khớp dẻo dai",
                    "Dạng nước dễ hấp thu",
                    "1 ống/ngày, dùng 3 tháng",
                ],
                "symptom": "Đau mỏi khớp gối khi đi bộ hoặc leo cầu thang hàng ngày",
                "benefit": "Kết hợp Collagen Peptides, tầm xuân & Vitamin C hỗ trợ sụn khớp",
                "hashtags": ["#collagen", "#sunkhop", "#bokhop", "#xuongkhopkhoe", "#baovesuckhoe"],
            },
            "kenh_3": {
                "cover_lines": [
                    "CH-Alpha Plus từ Đức",
                    "Dưỡng chất cho sụn khớp",
                    "Mỗi sáng 1 ống sau ăn",
                ],
                "symptom": "Chủ động chăm sóc sụn khớp linh hoạt mỗi ngày",
                "benefit": "Dạng ống uống liền nhập khẩu Đức hỗ trợ nuôi dưỡng mô sụn",
                "hashtags": ["#chalphaplus", "#collagensunkhop", "#duongkhop", "#vandonglinhhoat", "#chamsocsuckhoe"],
            },
        },
    },
    "biotin_forcapil": {
        "name": "Viên uống dưỡng tóc Biotin Pháp Arkopharma Forcapil",
        "short_name": "Dưỡng tóc Biotin Pháp",
        "seller_id": "7494727475325798000",
        "seller_name": "Shop Arkopharma Pháp (GMV Max - isAd: TRUE)",
        "product_id": "1729569737652668850",
        "dosage": "Ngày 2 viên buổi sáng",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Dưỡng tóc Biotin Pháp",
                    "Tóc yếu hay gãy rụng",
                    "Tóc con mọc lĩa chĩa",
                    "Mẹ sau sinh dùng được",
                ],
                "symptom": "Tóc yếu hay gãy rụng, rụng tóc nhiều sau sinh",
                "benefit": "Bổ sung Biotin, Kẽm & Vitamin B từ Pháp hỗ trợ tóc chắc khỏe",
                "hashtags": ["#forcapil", "#rungtocsausinh", "#rungtoc", "#arkopharma", "#biotin"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Rụng tóc sau sinh",
                    "Tóc mỏng, móng dễ gãy",
                    "Biotin Forcapil Pháp",
                    "Ngày 2 viên sau ăn sáng",
                ],
                "symptom": "Tóc thưa mỏng, gãy rụng nhiều khi chải đầu hoặc gội đầu",
                "benefit": "Hỗ trợ nuôi dưỡng nang tóc và móng khỏe mạnh từ bên trong",
                "hashtags": ["#duongtoc", "#biotin", "#forcapil", "#arkopharma", "#rungtoc"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Hỗ trợ giảm rụng tóc",
                    "Dưỡng tóc Biotin Pháp",
                    "Ngày 2 viên, dùng 3 tháng",
                ],
                "symptom": "Chăm sóc mái tóc dày mượt, hỗ trợ mọc tóc con chắc khỏe",
                "benefit": "Công thức Forcapil Pháp lành tính dùng được cho mẹ cho bé ti",
                "hashtags": ["#forcapil", "#rungtocsausinh", "#biotinphap", "#arkopharma", "#chamsocsuckhoe"],
            },
        },
    },
    "marial_gel": {
        "name": "Hỗn dịch dạ dày & trào ngược Marial Gel Ý (Hộp 20 gói)",
        "short_name": "Hỗn dịch dạ dày Marial Gel",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Chăm Sóc Sức Khỏe Chính Hãng (GMV Max - isAd: TRUE)",
        "product_id": "1738159842879505890",
        "dosage": "Xé uống liền 1 gói sau ăn hoặc khi đau rát",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Hỗn dịch dạ dày Marial Gel",
                    "Hỗ trợ trào ngược, đau bao tử",
                    "Ăn xong ngang ngực, ợ chua",
                    "Dạng gói xé uống liền tiện lợi",
                ],
                "symptom": "Đau rát dạ dày, ăn xong ngang ngực, ợ hơi ợ chua, trào ngược thực quản",
                "benefit": "Hỗ trợ làm dịu nhanh niêm mạc dạ dày & thực quản, giảm nóng rát khó chịu",
                "hashtags": ["#marialgel", "#traonguocdaday", "#daudaday", "#baotu", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Marial Gel — Bảo vệ Bao Tử",
                    "Giảm ợ hơi, ợ chua, nóng rát",
                    "Đau dạ dày ban đêm khó ngủ",
                    "1 gói sau ăn hoặc khi khó chịu",
                ],
                "symptom": "Hay đau bao tử thất thường vào ban đêm, nóng rát cổ họng do trào ngược",
                "benefit": "Dạng gói hỗn dịch uống liền từ Ý giúp bảo vệ niêm mạc bao tử êm ái",
                "hashtags": ["#marialgel", "#baotu", "#traonguoc", "#daudaday", "#suckhoegiadinh"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Trào ngược dạ dày thực quản",
                    "Đau rát bao tử, ngang ngực",
                    "Hỗn dịch Marial Gel từ Ý",
                    "Xé gói uống liền khi khó chịu",
                ],
                "symptom": "Đau dạ dày do ăn đồ chua cay hoặc dùng thuốc giảm đau dài ngày",
                "benefit": "Hỗn dịch Marial Gel hỗ trợ giảm nhanh trào ngược và bảo vệ niêm mạc",
                "hashtags": ["#marialgel", "#daubaotu", "#traonguocdaday", "#ochua", "#suckhoechudong"],
            },
        },
    },
    "ginkgo_bonao": {
        "name": "Viên uống dưỡng não Ginkgo Biloba Mỹ (Hộp 60 viên)",
        "short_name": "Dưỡng não Ginkgo Biloba Mỹ",
        "seller_id": "7494605437873326000",
        "seller_name": "Shop Mason Natural / Olympian Labs (GMV Max - isAd: TRUE)",
        "product_id": "1731468745270135099",
        "dosage": "Ngày uống 1 viên sau ăn",
        "angles": {
            "@suckhoeviet.2": {
                "cover_lines": [
                    "Dưỡng não Ginkgo Biloba Mỹ",
                    "Hỗ trợ tuần hoàn máu não",
                    "Hoa mắt, chóng mặt, tiền đình",
                    "Ngày uống 1 viên sau ăn",
                ],
                "symptom": "Đau đầu, hoa mắt, chóng mặt, ù tai, mất ngủ do thiểu năng tuần hoàn não",
                "benefit": "Hỗ trợ tăng cường tuần hoàn máu não, cải thiện rối loạn tiền đình",
                "hashtags": ["#ginkgobiloba", "#duongnao", "#tuanhoannao", "#roiloantiendinh", "#chamsocsuckhoe"],
            },
            "@suc.khoe.vang.268": {
                "cover_lines": [
                    "Hay đau đầu, mất ngủ, ù tai",
                    "Rối loạn tiền đình, chóng mặt",
                    "Viên uống Dưỡng Não từ Mỹ",
                    "1 viên/ngày, hộp dùng 2 tháng",
                ],
                "symptom": "Người lớn tuổi hay chóng mặt quay cuồng, đau nửa đầu, đêm khó ngủ",
                "benefit": "Bổ sung Ginkgo Biloba chuẩn Mỹ hỗ trợ máu lưu thông lên não tốt hơn",
                "hashtags": ["#bonao", "#ginkgobiloba", "#tiendinh", "#matngu", "#baovesuckhoe"],
            },
            "kenh_3": {
                "cover_lines": [
                    "Hỗ trợ rối loạn tiền đình",
                    "Giảm đau đầu, hoa mắt, ù tai",
                    "Dưỡng não Ginkgo Biloba Mỹ",
                    "Mỗi ngày 1 viên sau bữa ăn",
                ],
                "symptom": "Chăm sóc tuần hoàn máu não và trí nhớ cho người trưởng thành",
                "benefit": "Hộp 60 viên dùng trong 2 tháng giúp hỗ trợ giảm triệu chứng tiền đình",
                "hashtags": ["#ginkgobiloba", "#duongnaomy", "#tuanhoanmaunao", "#chongmat", "#suckhoechudong"],
            },
        },
    },
}

TYPO_FIXES = [
    (r"\bOmega\s*2\b", "Omega 3"),
    (r"\bViên\s+khớp\b", "Hỗ trợ khớp"),
    (r"\bthoát\s+hoá\b", "thoái hoá"),
    (r"\bthái\s+hoá\b", "thoái hoá"),
    (r"\bđau\s+nhứt\b", "đau nhức"),
    (r"\bCotrate\b", "Citrate"),
    (r"\bphucn\s+hồi\b", "phục hồi"),
]

BANNED_REPLACEMENTS = [
    (r"\b(Bác\s*sĩ|Bác\s*Sĩ|Bs\.?|BS\.?)\s+Chường\b", "Bác Chường"),
    (r"\b(Bác\s*sĩ|Bác\s*Sĩ|Bs\.?|BS\.?)\b", "Chuyên gia"),
    (r"\bhỗ\s+trợ\s+điều\s+trị\b", "hỗ trợ chăm sóc"),
    (r"\bđiều\s+trị\b", "hỗ trợ cải thiện"),
    (r"\bchữa\s+khỏi\b", "hỗ trợ giảm"),
    (r"\bdứt\s+điểm\b", "cải thiện rõ rệt"),
    (r"\bthương\s+hiệu\s+số\s+1\b", "thương hiệu uy tín"),
    (r"\bsố\s+dẫn\s+đầu\b", "uy tín lâu năm"),
    (r"\bcam\s+kết\s+khỏi\b", "hỗ trợ hiệu quả"),
]


def sanitize_tpcn_text(text: str) -> tuple[str, list[str]]:
    fixes_applied = []
    cleaned = text.strip()
    for pat, rep in TYPO_FIXES:
        if re.search(pat, cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
            fixes_applied.append(f"Sửa chính tả: '{pat}' -> '{rep}'")
    for pat, rep in BANNED_REPLACEMENTS:
        if re.search(pat, cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
            fixes_applied.append(f"Lọc từ nhạy cảm TPCN: '{pat}' -> '{rep}'")
    return cleaned, fixes_applied


def generate_batch_for_product(product_key: str, source_video: str = "input_raw/bac_chuong_source.mp4", base_start_sec: int = 10) -> list[dict]:
    if product_key not in PRODUCT_CATALOG:
        raise ValueError(f"Mã sản phẩm '{product_key}' không tồn tại")

    prod = PRODUCT_CATALOG[product_key]
    now = datetime.now()
    schedule_offsets_min = [15, 35, 55]
    variant_specs = [
        {"channel": "@suckhoeviet.2", "space": "Không gian 1 (Chính - Oppo A57)", "dur": 45, "zoom": 1.02, "speed": 1.00, "offset_sec": 0},
        {"channel": "@suc.khoe.vang.268", "space": "Không gian 2 (Bản sao - Oppo A57)", "dur": 48, "zoom": 1.04, "speed": 1.02, "offset_sec": 6},
        {"channel": "kenh_3", "space": "Kênh 3 (TikTok Studio Web R630)", "dur": 42, "zoom": 1.03, "speed": 0.99, "offset_sec": 12},
    ]

    items = []
    for idx, spec in enumerate(variant_specs):
        ch = spec["channel"]
        ang = prod["angles"][ch]
        cover_lines_str = "\n".join(ang["cover_lines"])
        raw_caption = (
            f"{ang['symptom']}\n"
            f"{prod['name']} — {ang['benefit']}\n"
            f"Cách dùng: {prod['dosage']}\n"
            f"{' '.join(ang['hashtags'])}"
        )
        clean_cover, f1 = sanitize_tpcn_text(cover_lines_str)
        clean_caption, f2 = sanitize_tpcn_text(raw_caption)
        sched_time = (now + timedelta(minutes=schedule_offsets_min[idx])).strftime("%H:%M · %d/%m/%Y")
        out_filename = f"{product_key}_{ch.replace('@', '').replace('.', '_')}_{now.strftime('%H%M%S')}.mp4"

        items.append({
            "id": f"{product_key}_{idx+1}_{int(now.timestamp())}",
            "channel": ch,
            "phone_space": spec["space"],
            "product_key": product_key,
            "product_name": prod["name"],
            "seller_id": prod["seller_id"],
            "seller_name": prod["seller_name"],
            "product_id": prod["product_id"],
            "scheduled_at": sched_time,
            "source_video": source_video,
            "output_video": f"output_ready/{out_filename}",
            "clip_start_sec": base_start_sec + spec["offset_sec"],
            "clip_duration_sec": spec["dur"],
            "unique_profile": {"zoom": spec["zoom"], "speed": spec["speed"], "strip_metadata": True},
            "cover_text": clean_cover,
            "caption_seo": clean_caption,
            "hashtags": ang["hashtags"],
            "seo_score": 100,
            "policy_fixes": f1 + f2,
            "status": "READY",
        })

    existing = []
    if QUEUE_FILE.exists():
        try:
            existing = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    QUEUE_FILE.write_text(json.dumps((items + existing)[:60], ensure_ascii=False, indent=2), encoding="utf-8")
    return items
