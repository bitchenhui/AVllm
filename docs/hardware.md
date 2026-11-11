# 硬件选择与跨机器对比

## 已有设备与分工

- M2 Max / 32GB 统一内存 / 1TB SSD：用户报告的家中闲置设备，优先作为专用 MLX 训练机。尚未远程执行环境检查或性能测试。
- M4 Pro / 24GB：在当前环境通过 sysctl 检测。用于开发、资料提取、数据审查和轻量试验。
- Core Ultra 7 356H / 32GB RAM / RTX 5060 Laptop 8GB：用户报告的 Windows 笔记本。可用于 4B 短样本 QLoRA 对照；系统内存不是高速独立显存，offload 有额外开销。

NVIDIA [笔记本官方规格](https://www.nvidia.com/en-us/geforce/laptops/50-series/) 与 [桌面规格](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5060-family/) 分开。笔记本功耗/散热和框架内核会影响持续训练速度，不用桌面基准代替笔记本实测，也不用游戏 FPS、NVENC 编码速度或标称 AI TOPS 推算 SFT 速度。

## 当前判断

能完全装入8GB的短样本任务，CUDA方案可能更快；这只是待验证预期。较长代码、更多激活或更大batch可能使8GB成为边界。32GB M2 Max 提供不同的容量空间，不能把统一内存和独显显存按字节简单等同。现有硬件先跑通，不根据尚不存在的速度数据购机。

新增 Mac mini 主要判断是否解决已测得的容量、常驻服务或日常机被占用问题。即使内存翻倍，GPU训练吞吐也不自动翻倍。Apple当前配置应以[在售技术规格](https://www.apple.com.cn/mac-mini/specs/)为准，旧M4机型支持页不代表当前在售型号；本方案不提供未经测量的购买收益倍数或价格。

## Windows CUDA 对照

可优先考虑 WSL2/Ubuntu 来匹配 Linux 训练工具链；原生 Windows 是否更方便取决于选定框架版本，不能保证所有加速组件可用。驱动与 PyTorch 必须支持 RTX50 的 Blackwell 架构，安装命令从 [PyTorch 官方选择器](https://pytorch.org/get-started/locally/)获取，不复制旧 CUDA 安装命令。

安装后用 `nvidia-smi` 和一次真实前向/反向矩阵运算检查；仅 `torch.cuda.is_available()` 为真还不足以证明所有训练内核兼容。4bit bitsandbytes 或其他内核也单独检查。参考已保存的 `materials/raw/training/llamafactory-qwen3-qlora.yaml`，将演示数据替换为同一审核数据，固定模型 revision、qwen3_nothink 模板和有效batch，先100步。

没有在Windows设备上执行安装、远程访问或训练。CUDA配置在实测前不标记为验证通过。MLX适配器与PEFT适配器的文件结构可能不同，不直接拷贝后宣称可续训。

## 短跑记录要求

保存每台机器的设备名、GPU核数/功耗、内存、系统、依赖版本、量化方式、实际target modules、训练层、rank、种子、真实token长度分布和数据hash。先排除下载/模型加载/编译预热时间，再报告稳定区间token/s；同时记录端到端用时，避免只报最好一步。

比较最终领域准确率与资源需求。若两后端不能采用等价适配范围或量化方式，明确两者是方案对比，不能把全部差异归于硬件。
