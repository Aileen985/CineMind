import torch
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from config import BLIP_MODEL_PATH,BLIP_MODEL_base_PATH
# ==================== 配置路径 ====================
# 微调后的模型路径
FINETUNED_MODEL_PATH = BLIP_MODEL_PATH

# 原始模型路径
ORIGINAL_MODEL_PATH = BLIP_MODEL_base_PATH

# 测试图片路径
TEST_IMAGE_PATH = "text.jpg"

# ==================== 加载模型 ====================
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"使用设备: {device}")

# 加载微调后的模型
print("\n加载微调模型...")
finetuned_processor = BlipProcessor.from_pretrained(FINETUNED_MODEL_PATH)
finetuned_model = BlipForConditionalGeneration.from_pretrained(FINETUNED_MODEL_PATH)
finetuned_model = finetuned_model.to(device)
finetuned_model.eval()

# 加载原始模型（对比用）
print("加载原始模型...")
original_processor = BlipProcessor.from_pretrained(ORIGINAL_MODEL_PATH)
original_model = BlipForConditionalGeneration.from_pretrained(ORIGINAL_MODEL_PATH)
original_model = original_model.to(device)
original_model.eval()

# ==================== 加载图片 ====================
try:
    image = Image.open(TEST_IMAGE_PATH).convert('RGB')
    print(f"图片加载成功: {TEST_IMAGE_PATH}")
except Exception as e:
    print(f"图片加载失败: {e}")
    exit()

# ==================== 测试函数 ====================
def generate_description(model, processor, image, device, max_new_tokens=80):
    """生成图片描述"""
    inputs = processor(image, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            num_beams=4,
            repetition_penalty=1.2,
            temperature=0.7
        )
    return processor.decode(out[0], skip_special_tokens=True)

# ==================== 运行测试 ====================
print("\n" + "="*60)
print("测试结果对比")
print("="*60)

# 原始模型输出
original_caption = generate_description(original_model, original_processor, image, device)
print(f"\n📌 原始BLIP描述:\n{original_caption}")

# 微调模型输出
finetuned_caption = generate_description(finetuned_model, finetuned_processor, image, device)
print(f"\n🎯 微调后描述:\n{finetuned_caption}")

print("\n" + "="*60)