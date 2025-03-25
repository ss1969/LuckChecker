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
from fnmatch import fnmatch

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
def parse_config_preprocessor_directive(line, defined_macros, condition_stack, skip_current_level, line_number=None):
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

# 处理配置文件某一行
def parse_config_single_line(line, config, line_number, in_swap_block):
    """处理配置文件某一行"""
    # 如果行首是{，说明是Swap块的开始
    if line.startswith('Swap = {'):
        if in_swap_block:
            print_error("大括号嵌套错误，已经在一个 Swap 块内", line, line_number)
            return config, in_swap_block, True  # 错误标志
        return config, True, False  # 进入Swap块，无错误
        
    # 如果行首是}，说明是Swap块的结束
    if line == '}':
        if not in_swap_block:
            print_error("发现未配对的结束大括号 '}'", line, line_number)
            return config, in_swap_block, True  # 错误标志
        return config, False, False  # 退出Swap块，无错误
        
    # 如果行首是typedef，说明是类型定义
    if line.startswith('typedef '):
        if not in_swap_block:
            print_error("typedef 必须在 Swap = { } 块内", line, line_number)
            return config, in_swap_block, True  # 错误标志
        if 'Swap' not in config:
            config['Swap'] = line
        else:
            config['Swap'] += ',' + line
        return config, in_swap_block, False
        
    # 如果行包含=，说明是键值对配置
    if '=' in line:
        key, value = map(str.strip, line.split('=', 1))
        # 处理行尾可能的逗号
        if value and value[-1] == ',':
            value = value[:-1].strip()

        # 对于Folder、Files、ExcludeFile和Swap键，追加到已有值
        if key in ['Folder', 'Files', 'Swap', 'ExcludeFile', 'ExcludeHeading']:
            if key not in config:
                config[key] = value
            else:
                # 如果已经有值，添加逗号分隔符
                if config[key]:
                    config[key] += ',' + value
                else:
                    config[key] = value
        else:
            config[key] = value
        return config, in_swap_block, False
        
    # 如果行不为空但不符合任何已知格式，报错
    if line:
        print_error("无效的配置行格式", line, line_number)
        return config, in_swap_block, True  # 错误标志
        
    return config, in_swap_block, False  # 空行，无错误

# 解析文件夹列表
def parse_config_folders(config):
    folders = []
    if 'Folder' in config:
        for folder_path in config['Folder'].split(','):
            folder_path = folder_path.strip()
            # 去除两边的引号（如果有）
            if folder_path.startswith('"') and folder_path.endswith('"'):
                folder_path = folder_path[1:-1]
            elif folder_path.startswith("'") and folder_path.endswith("'"):
                folder_path = folder_path[1:-1]
            if folder_path and folder_path not in folders:
                folders.append(folder_path)
    return folders

# 解析文件类型列表
def parse_config_files(config):
    files = []
    exclude_files = []
    
    if 'Files' in config:
        for pattern in config['Files'].split(','):
            pattern = pattern.strip()
            if pattern and pattern not in files:
                files.append(pattern)
                
    if 'ExcludeFile' in config:
        for pattern in config['ExcludeFile'].split(','):
            pattern = pattern.strip()
            # 去除两边的引号（如果有）
            if pattern.startswith('"') and pattern.endswith('"'):
                pattern = pattern[1:-1]
            elif pattern.startswith("'") and pattern.endswith("'"):
                pattern = pattern[1:-1]
            if pattern and pattern not in exclude_files:
                exclude_files.append(pattern)
                
    return files, exclude_files

# 处理typedef格式的替换规则
def parse_config_swap_typedef(part):
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
def parse_config_swaps(config, line_map=None):
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
                swap_pair = parse_config_swap_typedef(part)
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

# 解析排除前置标记列表
def parse_config_exclude_heading(config):
    """解析需要排除的前置标记列表"""
    exclude_heading = []
    if 'ExcludeHeading' in config:
        for heading in config['ExcludeHeading'].split(','):
            heading = heading.strip()
            # 去除两边的引号（如果有）
            if heading.startswith('"') and heading.endswith('"'):
                heading = heading[1:-1]
            elif heading.startswith("'") and heading.endswith("'"):
                heading = heading[1:-1]
            if heading and heading not in exclude_heading:
                exclude_heading.append(heading)
    return exclude_heading

# 解析配置文件
def parse_config(config_file):
    """解析配置文件"""
    config = {}
    in_swap_block = False
    has_error = False
    
    # 预定义宏
    defined_macros = {}
    
    # 条件指令状态栈
    condition_stack = []  # 存储当前条件指令的求值结果
    skip_current_level = False  # 是否跳过当前级别
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, 1):
                # 去除行首空格和行尾换行符
                line = line.strip()
                
                # 跳过空行和注释行
                if not line or line.startswith('//') or line.startswith('/*'):
                    continue
                    
                # 处理预处理指令
                if line.startswith('#'):
                    condition_stack, skip_current_level = parse_config_preprocessor_directive(
                        line, defined_macros, condition_stack, skip_current_level, line_number
                    )
                    continue
                    
                # 如果当前在跳过的条件块内，则跳过此行
                if skip_current_level:
                    continue
                    
                # 处理配置行
                config, in_swap_block, line_error = parse_config_single_line(line, config, line_number, in_swap_block)
                if line_error:
                    has_error = True
                    
        # 检查是否有未闭合的Swap块
        if in_swap_block:
            print_error("配置文件末尾缺少结束大括号 '}'", "", line_number)
            has_error = True
            
        # 检查是否有未闭合的条件指令
        if condition_stack:
            print_error(f"配置文件中有{len(condition_stack)}个未闭合的条件指令", "", line_number)
            has_error = True
            
        if has_error:
            print(f"{RED}配置文件解析失败，请检查上述错误{RESET}")
            return None
            
        return config
        
    except Exception as e:
        print(f"{RED}读取配置文件失败: {str(e)}{RESET}")
        return None

# 处理文件
def collect_replacements(original_lines, swaps, exclude_heading):
    """收集文件中的所有替换位置"""
    replacements_by_line = []
    total_replacements = 0

    for line_idx, orig_line in enumerate(original_lines):
        line_replacements = []
        line_copy = orig_line  # 使用行的副本来追踪已替换的位置
        # 用于跟踪已经处理过的位置区间
        processed_ranges = []

        # 检查当前行是否包含排除的前置标记
        exclude_heading_pos = -1
        if exclude_heading:
            for heading in exclude_heading:
                pos = orig_line.find(heading)
                if pos != -1:
                    exclude_heading_pos = pos
                    break

        # 收集这一行的所有替换
        for src, dest in swaps:  # swaps已经是排序后的规则
            # 修改正则表达式，确保匹配完整的独立单词
            # 使用零宽断言，确保单词前后是空白字符、标点符号或行首尾
            pattern = re.compile(r'(?<![a-zA-Z0-9_<]){0}(?![a-zA-Z0-9_>])'.format(re.escape(src)))
            # 查找所有匹配，但避免在已替换的位置上再次替换
            for match in pattern.finditer(orig_line):
                start, end = match.start(), match.end()

                # 如果这个替换位置在排除前置标记之后，则跳过
                if exclude_heading_pos != -1 and start > exclude_heading_pos:
                    continue

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
        prefix = f"{GRAY}LINE {line_num_str}:{RESET}  "

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
        print(f"{' ' * (len(prefix) - 12)}→  {colored_new_line}")

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

def find_pointer_definitions(filepath):
    """查找文件中的指针变量定义"""
    pointer_definitions = []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line_idx, line in enumerate(lines, 1):
            # 跳过空行和注释行
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('/*'):
                continue
                
            # 排除明显不是变量定义的行
            if '(' in line and ')' in line and '*' in line and line.index('(') < line.index('*'):
                # 可能是函数声明或定义，跳过
                continue
                
            # 查找指针定义的模式
            # 1. 基本指针变量: 类型 [const] *[const] 变量名 [= 初始值];
            # 2. 数组指针变量: 类型 [const] *[const] 变量名[] [= 初始值];
            # 3. 成员指针变量: 类型 类名::*变量名 [= 初始值];
            
            # 基本指针变量模式 - 使用\s+和\s*匹配多个空格或Tab
            basic_ptr_pattern = r'((?:const\s+)?(?:\w+)(?:::\w+)?(?:\s+const)?\s*\*+\s*(?:const\s+)?\s*(\w+))(?:\s*=\s*[^;]+)?;'
            
            # 数组指针变量模式 - 同样使用\s+和\s*匹配多个空格或Tab
            array_ptr_pattern = r'((?:const\s+)?(?:\w+)(?:::\w+)?(?:\s+const)?\s*\*+\s*(?:const\s+)?\s*(\w+)\s*\[\])(?:\s*=\s*[^;]+)?;'
            
            # 成员指针变量模式 - 同样使用\s+和\s*匹配多个空格或Tab
            member_ptr_pattern = r'((?:const\s+)?(?:\w+)\s+(\w+)::\*\s*(\w+))(?:\s*=\s*[^;]+)?;'
            
            # 查找所有匹配
            for pattern_name, pattern in [
                ("基本指针", basic_ptr_pattern),
                ("数组指针", array_ptr_pattern),
                ("成员指针", member_ptr_pattern)
            ]:
                for match in re.finditer(pattern, line):
                    if pattern_name == "基本指针" or pattern_name == "数组指针":
                        ptr_type = match.group(1)
                        ptr_name = match.group(2)
                    else:  # 成员指针
                        ptr_type = match.group(1)
                        class_name = match.group(2)
                        ptr_name = match.group(3)
                    
                    pointer_definitions.append((line_idx, ptr_type, pattern_name, line))
            
    except Exception as e:
        print(f"{RED}读取文件失败 {filepath}: {str(e)}{RESET}")
        
    return pointer_definitions

def display_pointer_definitions(filepath, definitions):
    """显示指针定义"""
    if not definitions:
        print(f"{GRAY}未找到指针定义{RESET}")
        return
        
    print(f"\n{CYAN}===== 指针定义列表 ====={RESET}")
    for line_idx, pointer_type, pointer_category, line in definitions:
        print(f"{GREEN}[{line_idx:4d}] {RESET}{RED}{pointer_type}{RESET} ({pointer_category})")
        print(f"      {line}")
    print(f"{CYAN}======================{RESET}\n")

def process_single_file(filepath, swaps, apply_changes, exclude_heading):
    """处理单个文件的替换操作"""
    with open(filepath, 'r', encoding='utf-8') as f:
        original_lines = f.readlines()

    # 收集替换位置
    replacements_by_line, total_replacements = collect_replacements(original_lines, swaps, exclude_heading)

    # 显示替换位置
    display_replacements(filepath, replacements_by_line)
    
    # 如果没有找到替换项目，显示提示信息
    if total_replacements == 0:
        print(f"{GRAY}没有查找到可替换项目{RESET}")

    # 查找并显示指针定义
    pointer_definitions = find_pointer_definitions(filepath)
    display_pointer_definitions(filepath, pointer_definitions)

    # 实际替换阶段
    if apply_changes and total_replacements > 0:
        modified, modified_lines = apply_replacements(original_lines, swaps)

        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(modified_lines)

    return total_replacements

# 显示配置信息并根据配置模式决定是否继续执行
def show_configuration(folders, files, exclude_files, swaps, config_only, exclude_heading):
    """显示程序配置信息，并根据配置模式决定是否继续执行"""
    print(f"{CYAN}===== 幸运检查工具 ====={RESET}")
    print(f"{GREEN}搜索目录: {RESET}{', '.join(folders)}")
    print(f"{GREEN}文件匹配: {RESET}{', '.join(files)}")
    if exclude_files:
        print(f"{GREEN}排除文件: {RESET}{', '.join(exclude_files)}")
    if exclude_heading:
        print(f"{GREEN}跳过包含: {RESET}{', '.join(exclude_heading)}")
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

# 收集目标文件列表
def collect_target_files(folders, files, exclude_files):
    """收集所有需要处理的文件列表"""
    # 首先收集所有匹配的文件
    matched_files = []

    for folder in folders:
        for root, _, filenames in os.walk(folder):
            for filename in filenames:
                # 检查是否匹配包含模式
                for pattern in files:
                    if pattern and fnmatch(filename, pattern.strip()):
                        filepath = os.path.join(root, filename)
                        matched_files.append(filepath)
                        break
    
    # 从匹配文件中排除不需要的文件
    if exclude_files:
        filtered_files = []
        for filepath in matched_files:
            filename = os.path.basename(filepath)
            exclude = False
            for pattern in exclude_files:
                if pattern and fnmatch(filename, pattern.strip()):
                    exclude = True
                    break
            if not exclude:
                filtered_files.append(filepath)
        matched_files = filtered_files

    print(f"\n{CYAN}===== 待处理文件文件列表 ====={RESET}")
    for i, filepath in enumerate(matched_files, 1):
        print(f"{GREEN}[{i:3d}] {RESET}{filepath}")
    print(f"{CYAN}======================{RESET}\n")

    return matched_files

# 查找并处理匹配文件
def process_matching_files(target_files, swaps, apply_changes, file_number=None, exclude_heading=None):
    """处理所有匹配的文件"""
    total = 0
    processed_files = 0
    current_file_index = 0

    # 处理文件列表
    for filepath in target_files:
        current_file_index += 1
        # 如果指定了文件序号且当前文件不是目标文件，则跳过
        if file_number is not None and current_file_index != file_number:
            continue

        abs_path = os.path.abspath(filepath)
        separator = "-" * 120
        print(f"{YELLOW}{separator}{RESET}")
        print(f"{YELLOW}处理文件 [{current_file_index}]: {abs_path}{RESET}")
        print(f"{YELLOW}{separator}{RESET}")

        count = process_single_file(filepath, swaps, apply_changes, exclude_heading)
        total += count
        processed_files += 1

        # 如果指定了文件序号且已处理完目标文件，则提前结束
        if file_number is not None and current_file_index == file_number:
            return total, processed_files

    return total, processed_files

# 显示处理结果
def display_results(total, processed_files, apply_changes):
    """显示处理结果"""
    print(f"\n{CYAN}===== 处理结果 ====={RESET}")
    print(f"总发现{total}处需要替换")
    print(f"{GREEN}{processed_files} Files Processed{RESET}")

    if not apply_changes:
        print("\n（本次仅为预览，添加-y参数实际执行修改）")

# 检查配置有效性
def check_config(folders, files, swaps):
    """检查配置的有效性"""
    if not folders:
        print_error("未指定搜索目录", None, 1)
        return False

    if not files:
        print_error("未指定文件类型", None, 1)
        return False

    if not swaps:
        print_error("未指定替换规则或替换规则存在错误", None, 1)
        return False

    # 检查目录是否存在
    missing_folders = [f for f in folders if not os.path.exists(f)]
    if missing_folders:
        print_error(f"目录不存在", None, 1, f"找不到目录: {', '.join(missing_folders)}")
        return False

    return True

def process_pointers_only(target_files, file_number=None):
    """只处理指针定义，不进行替换操作"""
    current_file_index = 0
    processed_files = 0
    total_pointers = 0

    # 处理文件列表
    for filepath in target_files:
        current_file_index += 1
        # 如果指定了文件序号且当前文件不是目标文件，则跳过
        if file_number is not None and file_number > 0 and current_file_index != file_number:
            continue

        abs_path = os.path.abspath(filepath)
        separator = "-" * 120
        print(f"{YELLOW}{separator}{RESET}")
        print(f"{YELLOW}分析文件 [{current_file_index}]: {abs_path}{RESET}")
        print(f"{YELLOW}{separator}{RESET}")

        # 查找并显示指针定义
        pointer_definitions = find_pointer_definitions(filepath)
        display_pointer_definitions(filepath, pointer_definitions)
        total_pointers += len(pointer_definitions)
        processed_files += 1

        # 如果指定了文件序号且已处理完目标文件，则提前结束
        if file_number is not None and file_number > 0 and current_file_index == file_number:
            break

    # 显示处理结果
    print(f"\n{CYAN}===== 指针分析结果 ====={RESET}")
    print(f"总共找到 {total_pointers} 个指针定义")
    print(f"{GREEN}{processed_files} 个文件已处理{RESET}")
    print(f"{CYAN}======================{RESET}\n")

# 主函数
def main():
    parser = argparse.ArgumentParser(description='幸运检查工具', prefix_chars='-/')
    parser.add_argument('-y', '--yes', nargs='?', const=0, type=int, dest='file_number',
                      help='实际执行文件修改。如果指定数字，则只处理该序号的文件（从1开始）')
    parser.add_argument('-c', '--config', dest='config_only', action='store_true',
                      help='只显示配置信息，不执行任何文件操作')
    parser.add_argument('-i', '--indicator', dest='pointer_only', action='store_true',
                      help='只显示指针定义，不处理替换项目')
    args = parser.parse_args()

    # 解析配置文件
    config = parse_config('config.ini')

    # 检查配置有效性
    if not check_config(parse_config_folders(config), parse_config_files(config)[0], parse_config_swaps(config)):
        return

    # 显示配置信息并决定是否继续执行
    if not show_configuration(parse_config_folders(config), parse_config_files(config)[0], parse_config_files(config)[1], parse_config_swaps(config), args.config_only, parse_config_exclude_heading(config)):
        return

    # 收集目标文件列表
    target_files = collect_target_files(parse_config_folders(config), parse_config_files(config)[0], parse_config_files(config)[1])

    # 如果是只显示指针模式，则只显示指针定义，不处理替换
    if args.pointer_only:
        process_pointers_only(target_files, args.file_number)
        return

    # 处理匹配的文件
    apply_changes = args.file_number is not None
    target_file_number = args.file_number if args.file_number and args.file_number > 0 else None
    
    total, processed_files = process_matching_files(target_files, parse_config_swaps(config), apply_changes, target_file_number, parse_config_exclude_heading(config))

    # 显示处理结果
    display_results(total, processed_files, apply_changes)

if __name__ == "__main__":
    main()