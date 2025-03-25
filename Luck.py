# 功能解释
# 1. 读取config.ini文件，获取需要替换的文件路径、文件类型、替换规则
# 2. 根据配置，进行替换
# 3. 打印需要替换的位置和替换内容
# 4. 如果添加-y参数，则实际执行替换
# 5. 如果添加-c参数，则只打印配置信息


import os
import re
import argparse
import colorama
from colorama import Fore, Style

colorama.init()

# 全局定义颜色变量
GRAY = Fore.LIGHTBLACK_EX
RED = Fore.RED
GREEN = Fore.GREEN
CYAN = Fore.CYAN
YELLOW = Fore.YELLOW
RESET = Style.RESET_ALL

# 打印错误信息
def print_error(message, line=None, line_number=None, additional_info=None):
    """统一打印错误信息的格式"""
    print(f"\n{RED}错误: {RESET}{message}")

    if line_number is not None:
        print(f"{RED}位置: {RESET}config.ini 文件第 {line_number} 行")

    if line is not None:
        print(f"{RED}内容: {RESET}{line}")

    if additional_info is not None:
        print(f"{RED}信息: {RESET}{additional_info}")

    print()  # 空行，使错误信息更清晰

# 处理预处理指令
def process_preprocessor_directive(line, defined_macros, condition_stack, skip_current_level, line_number=None):
    # 去除#后的前导空格
    line_content = line[1:].lstrip()

    # 处理#define
    if line_content.startswith('define '):
        if skip_current_level:
            return condition_stack, skip_current_level
        parts = line_content[7:].strip().split(' ', 1)
        if len(parts) >= 1:
            macro_name = parts[0]
            macro_value = parts[1] if len(parts) > 1 else "1"
            defined_macros[macro_name] = macro_value
        return condition_stack, skip_current_level

    # 处理#ifdef
    elif line_content.startswith('ifdef '):
        macro_name = line_content[6:].strip()
        is_defined = macro_name in defined_macros

        if condition_stack and not condition_stack[-1]:
            # 已经在一个false条件内，继续跳过
            condition_stack.append(False)
        else:
            condition_stack.append(is_defined)

        skip_current_level = not condition_stack[-1]
        return condition_stack, skip_current_level

    # 处理#ifndef
    elif line_content.startswith('ifndef '):
        macro_name = line_content[7:].strip()
        is_not_defined = macro_name not in defined_macros

        if condition_stack and not condition_stack[-1]:
            # 已经在一个false条件内，继续跳过
            condition_stack.append(False)
        else:
            condition_stack.append(is_not_defined)

        skip_current_level = not condition_stack[-1]
        return condition_stack, skip_current_level

    # 处理#if defined()
    elif line_content.startswith('if ') and 'defined' in line_content:
        match = re.search(r'defined\s*\(([^)]+)\)', line_content)
        if match:
            macro_name = match.group(1).strip()
            is_defined = macro_name in defined_macros

            if condition_stack and not condition_stack[-1]:
                # 已经在一个false条件内，继续跳过
                condition_stack.append(False)
            else:
                condition_stack.append(is_defined)

            skip_current_level = not condition_stack[-1]
        return condition_stack, skip_current_level

    # 处理通用的#if (新增处理宏值的比较)
    elif line_content.startswith('if ') and not 'defined' in line_content:
        if condition_stack and not condition_stack[-1]:
            # 已经在一个false条件内，继续跳过
            condition_stack.append(False)
            skip_current_level = True
            return condition_stack, skip_current_level

        # 提取条件表达式
        condition_expr = line_content[3:].strip()

        # 替换所有宏为其值
        for macro_name, macro_value in defined_macros.items():
            # 确保只替换完整的宏名，避免部分替换
            condition_expr = re.sub(r'\b{}\b'.format(re.escape(macro_name)), macro_value, condition_expr)

        # 尝试安全地计算表达式
        try:
            # 使用eval安全地计算表达式结果
            result = eval(condition_expr, {"__builtins__": {}}, {})
            condition_stack.append(bool(result))
        except:
            # 如果计算失败，假设条件为False
            print_error(f"无法计算条件表达式 '{condition_expr}'，默认为False", line, line_number)
            condition_stack.append(False)

        skip_current_level = not condition_stack[-1]
        return condition_stack, skip_current_level

    # 处理#elif
    elif line_content.startswith('elif '):
        if not condition_stack:
            print_error("在配置文件中发现未配对的#elif", line, line_number)
            return condition_stack, skip_current_level

        # 如果前面的条件已经为真，则跳过所有后续elif和else
        if any(condition_stack[:-1]):
            condition_stack[-1] = False
            skip_current_level = True
            return condition_stack, skip_current_level

        # 检查当前elif条件
        if 'defined(' in line_content:
            match = re.search(r'defined\s*\(([^)]+)\)', line_content)
            if match:
                macro_name = match.group(1).strip()
                is_defined = macro_name in defined_macros
                condition_stack[-1] = is_defined
                skip_current_level = not is_defined
        else:
            # 处理值比较的elif (类似#if的处理)
            condition_expr = line_content[5:].strip()

            # 替换所有宏为其值
            for macro_name, macro_value in defined_macros.items():
                condition_expr = re.sub(r'\b{}\b'.format(re.escape(macro_name)), macro_value, condition_expr)

            try:
                result = eval(condition_expr, {"__builtins__": {}}, {})
                condition_stack[-1] = bool(result)
            except:
                print_error(f"无法计算条件表达式 '{condition_expr}'，默认为False", line, line_number)
                condition_stack[-1] = False

            skip_current_level = not condition_stack[-1]

        return condition_stack, skip_current_level

    # 处理#else
    elif line_content.startswith('else'):
        if not condition_stack:
            print_error("在配置文件中发现未配对的#else", line, line_number)
            return condition_stack, skip_current_level

        # 如果之前的任何条件已经为真，那么else部分应该跳过
        if any(condition_stack[:-1]):
            skip_current_level = True
        else:
            # 否则，else部分的执行取决于之前最近的条件求反
            condition_stack[-1] = not condition_stack[-1]
            skip_current_level = not condition_stack[-1]
        return condition_stack, skip_current_level

    # 处理#endif
    elif line_content.startswith('endif'):
        if condition_stack:
            condition_stack.pop()
        else:
            print_error("在配置文件中发现未配对的#endif", line, line_number)

        # 更新skip_current_level状态
        skip_current_level = condition_stack and not condition_stack[-1]
        return condition_stack, skip_current_level

    return condition_stack, skip_current_level

# 处理配置行
def process_config_line(line, config, line_number, in_swap_block):
    if line.startswith('Swap = {'):
        if in_swap_block:
            print_error("大括号嵌套错误，已经在一个 Swap 块内", line, line_number)
            return config, in_swap_block, True  # 错误标志
        return config, True, False  # 进入Swap块，无错误

    if line == '}' and in_swap_block:
        return config, False, False  # 退出Swap块，无错误

    if line.startswith('typedef '):
        if not in_swap_block:
            print_error("typedef 必须在 Swap = { } 块内", line, line_number)
            return config, in_swap_block, True  # 错误标志
        if 'Swap' not in config:
            config['Swap'] = line
        else:
            config['Swap'] += ',' + line
    elif '=' in line:
        key, value = map(str.strip, line.split('=', 1))
        # 处理行尾可能的逗号
        if value and value[-1] == ',':
            value = value[:-1].strip()

        # 对于Folder、Files和Swap键，追加到已有值
        if key in ['Folder', 'Files', 'Swap']:
            if key not in config:
                config[key] = value
            else:
                config[key] += ',' + value
        else:
            config[key] = value

    return config, in_swap_block, False  # 无错误

# 解析文件夹列表
def parse_folders(config):
    folders = []
    if 'Folder' in config:
        for folder_path in config['Folder'].split(','):
            folder_path = folder_path.strip()
            if folder_path and folder_path not in folders:
                folders.append(folder_path)
    return folders

# 解析文件类型列表
def parse_files(config):
    files = []
    if 'Files' in config:
        for file_ext in config['Files'].split(','):
            file_ext = file_ext.strip()
            if file_ext and file_ext not in files:
                files.append(file_ext)
    return files

# 处理typedef格式的替换规则
def process_typedef_swap(part):
    # 移除注释部分
    if '/*' in part:
        part = part[:part.find('/*')].strip()
    elif '//' in part:
        part = part[:part.find('//')].strip()

    # 解析typedef语法
    # 格式: typedef [原类型] [新类型];
    match = re.match(r'typedef\s+(.*?)\s+(\w+)\s*;', part)
    if match:
        src_type = match.group(1).strip()  # 原类型
        dest_type = match.group(2).strip() # 新类型
        return f"{src_type}/{dest_type}"
    return None

# 解析替换规则
def parse_swaps(config, line_map=None):
    swaps = []
    source_set = set()  # 用于检测重复的源类型

    # 跟踪每个源类型的定义位置和行内容（用于错误提示）
    source_locations = {}

    if 'Swap' in config:
        # 分割Swap值，处理引号情况
        pairs = []
        swap_value = config['Swap']

        # 处理传统Swap格式和typedef格式
        for part in swap_value.split(','):
            part = part.strip()
            if not part:
                continue

            # 处理typedef格式
            if part.startswith('typedef '):
                swap_pair = process_typedef_swap(part)
                if swap_pair:
                    pairs.append((swap_pair, part))  # 添加源代码用于错误提示
            else:
                pairs.append((part, part))  # 添加源代码用于错误提示

        # 处理传统的 src/dest 格式
        for pair_info in pairs:
            pair, original_text = pair_info
            if '/' in pair:
                parts = pair.split('/', 1)
                if len(parts) == 2:
                    src, dest = parts[0].strip(), parts[1].strip()
                    # 移除可能的引号
                    if src.startswith('"') and src.endswith('"'):
                        src = src[1:-1]
                    if dest.startswith('"') and dest.endswith('"'):
                        dest = dest[1:-1]
                    if src and dest:  # 确保源和目标都不为空
                        # 检查是否有重复的源
                        if src in source_set:
                            line_num = None
                            if line_map and original_text in line_map:
                                line_num = line_map[original_text]
                            previous_line = source_locations.get(src, None)

                            print_error(
                                f"替换规则中存在重复的源类型 '{src}'",
                                original_text,
                                line_num,
                                f"之前定义: {previous_line}" if previous_line else None
                            )
                            return []
                        source_set.add(src)
                        source_locations[src] = original_text  # 记录源类型的定义位置
                        swaps.append((src, dest))

    # 对替换规则按长度降序排序
    swaps.sort(key=lambda x: len(x[0]), reverse=True)

    return swaps

# 解析配置文件
def parse_config(config_path):
    config = {}
    # 跟踪每行内容的行号（用于错误提示）
    line_map = {}

    # 预定义宏
    defined_macros = {}

    # 条件指令状态栈
    condition_stack = []  # 存储当前条件指令的求值结果
    skip_current_level = False  # 是否跳过当前级别

    # Swap块状态
    in_swap_block = False

    # 记录最后一行行号，用于未闭合块错误提示
    last_line_number = 0

    # 有效的预处理指令关键字
    valid_preprocessor_keywords = ['ifdef', 'ifndef', 'if', 'elif', 'else', 'endif', 'define']

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                last_line_number = line_number
                # 保存原始行内容
                original_line = line.strip()
                # 保存每行内容对应的行号
                if original_line:
                    line_map[original_line] = line_number

                # 处理可能有前导空格的预处理指令
                if original_line and original_line.lstrip().startswith('#'):
                    # 提取预处理指令（去除前导空格）
                    preprocessor_line = original_line.lstrip()

                    # 验证预处理指令的有效性
                    is_valid = False

                    # 允许#和关键字之间有空格
                    preprocessor_parts = preprocessor_line[1:].lstrip().split(None, 1)
                    if preprocessor_parts:
                        first_keyword = preprocessor_parts[0]
                        if first_keyword in valid_preprocessor_keywords:
                            is_valid = True

                    # 如果预处理指令无效，报错
                    if not is_valid:
                        first_word = preprocessor_line.split(None, 1)[0][1:] if ' ' in preprocessor_line else preprocessor_line[1:]
                        print_error(
                            f"无效的预处理指令 '{first_word}'",
                            original_line,
                            line_number,
                            f"有效的预处理指令关键字: {', '.join(valid_preprocessor_keywords)}"
                        )
                        return [], [], []

                    # 处理预处理器指令
                    try:
                        condition_stack, skip_current_level = process_preprocessor_directive(
                            preprocessor_line, defined_macros, condition_stack, skip_current_level, line_number
                        )
                    except Exception as e:
                        print_error(
                            "处理预处理指令时出错",
                            original_line,
                            line_number,
                            str(e)
                        )
                        return [], [], []
                    continue
                # 忽略空行和注释行（// 或 /* 开头）
                elif (not original_line or
                      original_line.lstrip().startswith('//') or
                      original_line.lstrip().startswith('/*')):
                    continue

                # 如果当前在跳过的条件块内，则跳过此行
                if skip_current_level:
                    continue

                # 正常处理配置行
                config, in_swap_block, has_error = process_config_line(original_line, config, line_number, in_swap_block)
                if has_error:
                    print_error("配置文件解析中断，请修复错误后重试", original_line, line_number)
                    return [], [], []
    except Exception as e:
        print_error(f"配置文件解析错误", None, last_line_number, str(e))
        return [], [], []

    # 检查是否有未闭合的块
    if in_swap_block:
        print_error("配置文件中有未闭合的 Swap 块，缺少结束大括号 '}'", None, last_line_number)
        return [], [], []

    # 检查是否有未闭合的条件指令
    if condition_stack:
        print_error(f"配置文件中有{len(condition_stack)}个未闭合的条件指令", None, last_line_number)

    # 解析各部分配置
    folders = parse_folders(config)
    files = parse_files(config)
    swaps = parse_swaps(config, line_map)

    return folders, files, swaps

# 打印替换信息
def print_replace_info(filename, line_num, pre, original, post, dest):
    # 处理字符串中的换行符
    pre = pre.replace('\n', '\\n').lstrip()
    original = original.replace('\n', '\\n')
    post = post.replace('\n', '\\n')
    dest = dest.replace('\n', '\\n')

    # 计算显示内容 - 直接使用颜色而不包含在格式化字符串中
    original_colored = f"{pre}{RED}{original}{RESET}{GRAY}{post}{RESET}"
    new_colored = f"{pre}{GREEN}{dest}{RESET}{GRAY}{post}{RESET}"

    # 构建前缀（文件名和行号）
    if filename and line_num:
        # 行号以4位显示，不足补0
        line_num_str = f"{line_num:04d}"
        prefix = f"LINE {line_num_str}:  "
    else:
        # 使用空格对齐后续行
        prefix = " " * 12  # 根据"LINE 0000: "的长度调整

    # 不要在格式化宽度中包含颜色控制字符，先计算显示长度
    # 计算不含颜色控制字符的显示长度
    visible_len = len(pre) + len(original) + len(post)

    # 不使用格式化宽度，而是手动计算和添加空格
    padding = max(0, 40 - visible_len)
    spacing = " " * padding

    # 打印最终结果
    print(f"{prefix}{GRAY}{original_colored}{spacing} →     {new_colored}")

# 处理文件
def collect_replacements(original_lines, swaps):
    """收集文件中的所有替换位置"""
    replacements_by_line = []
    total_replacements = 0

    for line_idx, orig_line in enumerate(original_lines):
        line_replacements = []
        line_copy = orig_line  # 使用行的副本来追踪已替换的位置
        # 用于跟踪已经处理过的位置区间
        processed_ranges = []

        # 收集这一行的所有替换
        for src, dest in swaps:  # swaps已经是排序后的规则
            # 修改正则表达式，确保匹配完整的独立单词
            # 使用零宽断言，确保单词前后是空白字符、标点符号或行首尾
            pattern = re.compile(r'(?<![a-zA-Z0-9_<]){0}(?![a-zA-Z0-9_>])'.format(re.escape(src)))
            # 查找所有匹配，但避免在已替换的位置上再次替换
            for match in pattern.finditer(orig_line):
                start, end = match.start(), match.end()

                # 检查这个范围是否已经被处理过
                overlap = False
                for p_start, p_end in processed_ranges:
                    # 检查是否有重叠
                    if (start <= p_end and end >= p_start):
                        overlap = True
                        break

                if overlap:
                    continue

                pre = orig_line[max(0, start-10):start]
                original = orig_line[start:end]
                post = orig_line[end:end+10]

                # 检查这个位置是否已经被替换过
                if original == src:  # 确保完全匹配原始字符串
                    # 将start和end也加入到替换信息中
                    line_replacements.append((pre, original, post, dest, start, end))
                    # 记录已处理的范围
                    processed_ranges.append((start, end))

        if line_replacements:
            # 按位置排序，从前到后
            line_replacements.sort(key=lambda x: x[4])  # 使用start位置来排序
            replacements_by_line.append((line_idx, line_replacements))
            total_replacements += len(line_replacements)

    return replacements_by_line, total_replacements

# 显示所有替换位置
def display_replacements(filepath, replacements_by_line):
    rel_path = os.path.relpath(filepath)

    # 读取文件内容
    with open(filepath, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    for line_idx, line_replacements in replacements_by_line:
        # 获取原始行内容
        original_line = original_lines[line_idx]

        # 构建前缀（行号）
        line_num_str = f"{line_idx + 1:04d}"
        prefix = f"LINE {line_num_str}:  "

        # 创建原始行，不包含任何着色
        old_line = original_line

        # 创建新行（应用所有替换）
        new_line = original_line
        # 从后向前替换，避免位置偏移
        for pre, original, post, dest, start, end in sorted(line_replacements, key=lambda x: x[4], reverse=True):
            new_line = new_line[:start] + dest + new_line[end:]

        # 为原始行和新行添加彩色标记
        # 原始行：每个被替换的部分标记为红色
        colored_segments_old = []
        last_pos = 0

        for pre, original, post, dest, start, end in sorted(line_replacements, key=lambda x: x[4]):
            # 添加未替换的部分
            if start > last_pos:
                segment = old_line[last_pos:start]
                colored_segments_old.append(segment)
            # 添加替换的部分（红色）
            colored_segments_old.append(f"{RED}{original}{RESET}")
            last_pos = end

        # 添加最后一部分
        if last_pos < len(old_line):
            segment = old_line[last_pos:]
            colored_segments_old.append(segment)

        # 新行：计算替换后的新位置
        new_positions = []
        offset = 0

        for pre, original, post, dest, start, end in sorted(line_replacements, key=lambda x: x[4]):
            new_pos = start + offset
            new_positions.append((new_pos, dest))
            offset += len(dest) - len(original)

        # 为新行添加彩色标记
        colored_segments_new = []
        last_pos = 0

        for pos, dest in new_positions:
            # 添加未替换的部分
            if pos > last_pos:
                segment = new_line[last_pos:pos]
                colored_segments_new.append(segment)
            # 添加替换的部分（绿色）
            colored_segments_new.append(f"{GREEN}{dest}{RESET}")
            last_pos = pos + len(dest)

        # 添加最后一部分
        if last_pos < len(new_line):
            segment = new_line[last_pos:]
            colored_segments_new.append(segment)

        # 组合成最终的彩色字符串
        colored_old_line = ''.join(colored_segments_old).strip()
        colored_new_line = ''.join(colored_segments_new).strip()

        # 打印旧行和新行
        print(f"{prefix}{colored_old_line}")
        print(f"{' ' * (len(prefix) - 3)}→  {colored_new_line}")

def apply_replacements(original_lines, swaps):
    """应用替换到文件内容"""
    modified = False
    modified_lines = original_lines.copy()

    for line_idx in range(len(modified_lines)):
        new_line = modified_lines[line_idx]
        for src, dest in swaps:
            # 修改正则表达式，确保匹配完整的独立单词
            # 使用零宽断言，确保单词前后是空白字符、标点符号或行首尾
            pattern = re.compile(r'(?<![a-zA-Z0-9_<]){0}(?![a-zA-Z0-9_>])'.format(re.escape(src)))
            new_line, count = pattern.subn(dest, new_line)
            if count > 0:
                modified = True
        modified_lines[line_idx] = new_line

    return modified, modified_lines

def process_file(filepath, swaps, apply_changes):
    """处理单个文件的替换操作"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    # 收集替换位置
    replacements_by_line, total_replacements = collect_replacements(original_lines, swaps)

    # 显示替换位置
    display_replacements(filepath, replacements_by_line)

    # 实际替换阶段
    if apply_changes and total_replacements > 0:
        modified, modified_lines = apply_replacements(original_lines, swaps)

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)

    return total_replacements

# 显示配置信息并根据配置模式决定是否继续执行
def show_configuration(folders, files, swaps, config_only):
    """显示程序配置信息，并根据配置模式决定是否继续执行"""
    print(f"{CYAN}===== 幸替换运工具 ====={RESET}")
    print(f"{GREEN}搜索目录: {RESET}{', '.join(folders)}")
    print(f"{GREEN}文件类型: {RESET}{', '.join(files)}")
    if config_only:
        print(f"{GREEN}替换规则: {RESET}")
        # 找出最长的src长度
        max_src_len = max(len(src) for src, _ in swaps) if swaps else 0
        for src, dest in swaps:
            print(f"  {RED}{src.ljust(max_src_len)}{RESET} → {GREEN}{dest}{RESET}")
        print(f"{CYAN}======================{RESET}")
        print(f"\n{YELLOW}配置预览模式: 不执行实际文件操作{RESET}")
        print(f"{GREEN}替换规则: {RESET}{len(swaps)} 条")
        return False
    print(f"{GREEN}替换规则: {RESET}{len(swaps)} 条")
    return True

# 检查配置有效性
def check_config(folders, files, swaps):
    """检查配置的有效性"""
    if not folders:
        print_error("未指定搜索目录", None, 1)  # 假设在配置文件开始处检查
        return False

    if not files:
        print_error("未指定文件类型", None, 1)  # 假设在配置文件开始处检查
        return False

    if not swaps:
        print_error("未指定替换规则或替换规则存在错误", None, 1)  # 假设在配置文件开始处检查
        return False

    # 检查目录是否存在
    missing_folders = [f for f in folders if not os.path.exists(f)]
    if missing_folders:
        print_error(f"目录不存在", None, 1, f"找不到目录: {', '.join(missing_folders)}")  # 假设在配置文件开始处检查
        return False

    return True

# 查找并处理匹配文件
def process_matching_files(folders, files, swaps, apply_changes):
    """查找并处理所有匹配的文件"""
    total = 0
    processed_files = 0

    # 遍历所有目录
    for folder in folders:
        for root, _, filenames in os.walk(folder):
            for filename in filenames:
                if any(filename.endswith(ext) for ext in files):
                    filepath = os.path.join(root, filename)
                    abs_path = os.path.abspath(filepath)

                    separator = "-" * 80
                    print(f"\n{YELLOW}{separator}{RESET}")
                    print(f"{YELLOW}处理文件: {abs_path}{RESET}")
                    print(f"{YELLOW}{separator}{RESET}")

                    count = process_file(filepath, swaps, apply_changes)
                    total += count
                    processed_files += 1

    return total, processed_files

# 显示处理结果
def display_results(total, processed_files, apply_changes):
    """显示处理结果"""
    print(f"\n{CYAN}===== 处理结果 ====={RESET}")
    print(f"总发现{total}处需要替换")
    print(f"{GREEN}{processed_files} Files Processed{RESET}")

    if not apply_changes:
        print("\n（本次仅为预览，添加-y参数实际执行修改）")

# 主函数
def main():
    parser = argparse.ArgumentParser(description='幸替换运工具', prefix_chars='-/')
    parser.add_argument('-y', '--yes', dest='apply_changes', action='store_true',
                      help='实际执行文件修改（不加此参数仅显示预览）')
    parser.add_argument('-c', '--config', dest='config_only', action='store_true',
                      help='只显示配置信息，不执行任何文件操作')
    args = parser.parse_args()

    # 解析配置文件
    folders, files, swaps = parse_config('config.ini')

    # 检查配置有效性
    if not check_config(folders, files, swaps):
        return

    # 显示配置信息并决定是否继续执行
    if not show_configuration(folders, files, swaps, args.config_only):
        return

    # 处理匹配的文件
    total, processed_files = process_matching_files(folders, files, swaps, args.apply_changes)

    # 显示处理结果
    display_results(total, processed_files, args.apply_changes)

if __name__ == "__main__":
    main()