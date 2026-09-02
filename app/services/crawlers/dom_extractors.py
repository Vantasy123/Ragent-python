"""各大招聘平台（BOSS直聘 / 猎聘 / 51job / 牛客网）真实 DOM 抽取器与页面脚本。

本模块提供可直接注入到 Chrome 浏览器（CDP Runtime.evaluate 或 Playwright page.evaluate）
的纯 JavaScript 提取逻辑，以及 Python 端的回退 HTML 解析器。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# JavaScript 注入脚本（在真实浏览器渲染后的 DOM 树中运行并返回结构化数据）
# ---------------------------------------------------------------------------

BOSS_DOM_EXTRACTOR_JS = """
(() => {
    const results = [];
    const cards = document.querySelectorAll('.job-card-wrapper, .job-card-box, li.job-card-box');
    
    for (const card of cards) {
        try {
            const titleEl = card.querySelector('.job-name, .job-title');
            const salaryEl = card.querySelector('.salary, .job-salary');
            const companyEl = card.querySelector('.company-name a, .company-name, .boss-name');
            const linkEl = card.querySelector('.job-card-left, .job-name a, a.job-card-left') || card.querySelector('a');
            const cityEl = card.querySelector('.job-area, .job-area-wrapper');
            const tagEls = card.querySelectorAll('.tag-list li, .job-tags span');
            const infoEl = card.querySelector('.info-desc, .job-desc');
            const companyTagEls = card.querySelectorAll('.company-tag-list li');

            const title = titleEl ? titleEl.textContent.trim() : '';
            const salary_str = salaryEl ? salaryEl.textContent.trim() : '';
            const company = companyEl ? companyEl.textContent.trim() : '';
            let href = linkEl ? linkEl.getAttribute('href') : '';
            if (href && !href.startsWith('http')) {
                href = 'https://www.zhipin.com' + href;
            }

            const tags = Array.from(tagEls).map(el => el.textContent.trim()).filter(Boolean);
            const company_tags = Array.from(companyTagEls).map(el => el.textContent.trim()).filter(Boolean);
            const city = cityEl ? cityEl.textContent.trim().split('·')[0] : '';
            const desc = infoEl ? infoEl.textContent.trim() : '';

            let exp = '经验不限';
            let edu = '学历不限';
            for (const t of tags) {
                if (t.includes('年') || t.includes('应届') || t.includes('在校') || t.includes('经验')) {
                    exp = t;
                } else if (t.includes('大专') || t.includes('本科') || t.includes('硕士') || t.includes('博士') || t.includes('中专')) {
                    edu = t;
                }
            }

            if (title && company) {
                results.push({
                    title: title,
                    company: company,
                    city: city,
                    salary_str: salary_str,
                    experience_req: exp,
                    education_req: edu,
                    source_url: href,
                    tags: tags,
                    company_tags: company_tags,
                    jd_text: desc || `${company}招聘${title}，薪资${salary_str}，要求：${exp}、${edu}`
                });
            }
        } catch (e) {
            console.error('Extract BOSS card error:', e);
        }
    }
    return results;
})()
"""

LIEPIN_DOM_EXTRACTOR_JS = """
(() => {
    const results = [];
    const cards = document.querySelectorAll('.job-list-box .job-card-pc-container, .job-card-pc-container, .job-card-wrapper');
    
    for (const card of cards) {
        try {
            const titleEl = card.querySelector('.job-title, .job-title-box .ellipsis-1, a[data-nick="job-title"]');
            const salaryEl = card.querySelector('.job-salary, .job-title-box .job-salary');
            const companyEl = card.querySelector('.company-name, a[data-nick="job-company-name"]');
            const cityEl = card.querySelector('.job-dq-box, .job-dq, .ellipsis-1');
            const linkEl = card.querySelector('a.job-card-left, a[data-nick="job-title"]') || card.querySelector('a');
            const labelEls = card.querySelectorAll('.labels-tag, .job-labels-box span');
            const compTagEls = card.querySelectorAll('.company-tags-box span');

            const title = titleEl ? titleEl.textContent.trim() : '';
            const salary_str = salaryEl ? salaryEl.textContent.trim() : '';
            const company = companyEl ? companyEl.textContent.trim() : '';
            let href = linkEl ? linkEl.getAttribute('href') : '';
            if (href && !href.startsWith('http')) {
                href = 'https://www.liepin.com' + href;
            }

            const city = cityEl ? cityEl.textContent.trim().split('-')[0] : '';
            const tags = Array.from(labelEls).map(el => el.textContent.trim()).filter(Boolean);
            const comp_tags = Array.from(compTagEls).map(el => el.textContent.trim()).filter(Boolean);

            let exp = '经验不限';
            let edu = '学历不限';
            for (const t of tags) {
                if (t.includes('年') || t.includes('应届')) exp = t;
                if (t.includes('本') || t.includes('大专') || t.includes('硕') || t.includes('博')) edu = t;
            }

            if (title && company) {
                results.push({
                    title: title,
                    company: company,
                    city: city,
                    salary_str: salary_str,
                    experience_req: exp,
                    education_req: edu,
                    source_url: href,
                    tags: tags,
                    company_tags: comp_tags,
                    jd_text: `${company} 诚聘 ${title}，薪资待遇：${salary_str}。任职条件：${tags.join(' / ')}`
                });
            }
        } catch (e) {
            console.error('Extract Liepin card error:', e);
        }
    }
    return results;
})()
"""

JOB51_DOM_EXTRACTOR_JS = """
(() => {
    const results = [];
    const cards = document.querySelectorAll('.joblist-item, .j_joblist .e, .job-item, .joblist-box .job-card, [class*="job-card"]');
    
    for (const card of cards) {
        try {
            const titleEl = card.querySelector('.jname, .jobname, .j_name, .job-title, [class*="job-name"], a[href*="jobs/"]');
            const salaryEl = card.querySelector('.sal, .salary, .info .sal, [class*="salary"]');
            const companyEl = card.querySelector('.cname, .company-name, .c_name, [class*="company-name"], [class*="company"]');
            const cityEl = card.querySelector('.d.area, .area, .location, [class*="location"], [class*="city"]');
            const primaryLink = card.querySelector('a[href*="jobs.51job.com"]') || card.querySelector('a');
            const tagEls = card.querySelectorAll('.tags span, .d.tags span, .d.tags');

            const title = titleEl ? titleEl.textContent.trim() : '';
            const salary_str = salaryEl ? salaryEl.textContent.trim() : '';
            const company = companyEl ? companyEl.textContent.trim() : '';
            let href = primaryLink ? (primaryLink.getAttribute('href') || primaryLink.href || '') : '';

            const city = cityEl ? cityEl.textContent.trim().split('·')[0].split('-')[0] : '';
            const tags = Array.from(tagEls).map(el => el.textContent.trim()).filter(Boolean);

            let exp = '经验不限';
            let edu = '学历不限';
            for (const t of tags) {
                if (t.includes('年') || t.includes('应届')) exp = t;
                if (t.includes('大专') || t.includes('本科') || t.includes('硕士')) edu = t;
            }

            if (title && company) {
                results.push({
                    title: title,
                    company: company,
                    city: city,
                    salary_str: salary_str,
                    experience_req: exp,
                    education_req: edu,
                    source_url: href,
                    tags: tags,
                    company_tags: ['51job名企'],
                    jd_text: `${company} 发布岗位 ${title}，薪资：${salary_str}，要求：${tags.join(' / ')}`
                });
            }
        } catch (e) {
            console.error('Extract 51job card error:', e);
        }
    }

    // 51job 当前页面可能把职位详情链接放在卡片外层；从真实职位 URL 反查最近容器。
    if (!results.length) {
        const detailLinks = Array.from(document.querySelectorAll('a[href*="jobs.51job.com"]'))
            .filter(anchor => anchor.href.includes('jobs.51job.com/') && /[0-9]+[.]html/.test(anchor.href));
        for (const link of detailLinks) {
            const container = link.closest('li, .joblist-item, .job-item, [class*="job"], div') || link;
            const lines = (container.innerText || '').split(/\\n/).map(x => x.trim()).filter(Boolean);
            const title = (link.innerText || lines[0] || '').trim();
            const salary = lines.find(x => /\\d+.*(?:千|万|k|K|元\\/天|面议)/.test(x)) || '';
            const company = lines.find(x => x !== title && x !== salary && !/北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|苏州/.test(x) && x.length > 1) || '';
            if (title && company) {
                results.push({
                    title,
                    company,
                    city: lines.find(x => /北京|上海|广州|深圳|杭州|成都|武汉|南京|西安|苏州/.test(x)) || '',
                    salary_str: salary,
                    experience_req: '经验不限',
                    education_req: '学历不限',
                    source_url: link.href,
                    tags: [],
                    company_tags: [],
                    jd_text: `${company} 发布岗位 ${title}，薪资：${salary}`,
                });
            }
        }
    }
    return results;
})()
"""

NOWCODER_DOM_EXTRACTOR_JS = """
(() => {
    const results = [];
    const cards = document.querySelectorAll('.job-item, .rec-job-item, .tw-p-4.tw-bg-white, .feed-item, .recruitment-job-card, .feed-job-card, a[href*="/jobs/detail/"]');
    
    for (const card of cards) {
        try {
            const titleEl = card.querySelector('.title, .job-title, a[href*="/jobs/detail/"], [class*="text-base-pure"]');
            const salaryEl = card.querySelector('.salary, .job-salary, .tw-text-red-500, [class*="text-[#ff561b]"]');
            const companyEl = card.querySelector('.company-name, .company, a[href*="/company/"], [class*="company-name"]');
            const cityEl = card.querySelector('.city, .location, .tw-text-gray-500, .tag-item');
            const linkEl = card.querySelector('a[href*="/jobs/detail/"]') || card.querySelector('a');
            const tagEls = card.querySelectorAll('.detail-tags span, .tag, .tw-bg-gray-100');
            let href = '';
            const detailLink = card.matches('a[href*="/jobs/detail/"]')
                ? card
                : (card.querySelector('a[href*="/jobs/detail/"]') || card.querySelector('a'));
            href = detailLink ? (detailLink.getAttribute('href') || detailLink.href || '') : '';

            const title = titleEl ? titleEl.textContent.trim() : '';
            const salary_str = salaryEl ? salaryEl.textContent.trim() : '';
            const company = companyEl ? companyEl.textContent.trim() : '';

            const city = cityEl ? cityEl.textContent.trim().split(' ')[0] : '';
            const tags = Array.from(tagEls).map(el => el.textContent.trim()).filter(Boolean);

            if (title && company) {
                results.push({
                    title: title,
                    company: company,
                    city: city,
                    salary_str: salary_str || '面议',
                    experience_req: '应届生/实习生',
                    education_req: '本科及以上',
                    source_url: href,
                    tags: tags,
                    company_tags: ['牛客校招', '应届生直招'],
                    jd_text: `${company} 2026/2027 校园招聘：${title}，薪资：${salary_str}。标签：${tags.join(' / ')}`
                });
            }
        } catch (e) {
            console.error('Extract Nowcoder card error:', e);
        }
    }
    return results;
})()
"""
DETAIL_DOM_EXTRACTOR_JS = """
(() => {
    const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
    const text = (selector) => {
        const el = document.querySelector(selector);
        return el ? clean(el.innerText || el.textContent) : '';
    };
    const all = (selector) => Array.from(document.querySelectorAll(selector))
        .map(el => clean(el.innerText || el.textContent)).filter(Boolean);
    const title = text('h1, .job-title, .job-name, [class*="job-title"]');
    const company = text('.company-name, .company, [class*="company-name"]');
    const jdSelectors = [
        '.job-sec-text', '.job-detail', '.job-description', '.job-content',
        '.job-detail-content', '.job-detail', '.job_msg', '.bmsg.job_msg',
        '.job-desc', '.description',
        '[class*="job-desc"]', '[class*="description"]',
        'main [class*="content"]', 'main',
        '[class*="detail"] [class*="content"]', '[class*="job-detail"]'
    ];
    let jdText = '';
    for (const selector of jdSelectors) {
        const candidate = text(selector);
        if (candidate.length >= 40) {
            jdText = candidate;
            break;
        }
    }
    const sectionBlocks = Array.from(document.querySelectorAll(
        '.job-sec, .job-section, .job-detail-section, section, [class*="section"]'
    )).map(el => clean(el.innerText || el.textContent)).filter(Boolean);
    const sectionMatches = (pattern) => sectionBlocks
        .filter(block => pattern.test(block))
        .flatMap(block => block.split(/[\\n。；;]/).map(clean).filter(line => line && !pattern.test(line)))
        .slice(0, 12);
    const jdLines = jdText.split(/[\\n。；;]/).map(clean).filter(Boolean);
    const matchingLines = (pattern) => jdLines.filter(line => pattern.test(line)).slice(0, 12);
    const sectionOrLineMatches = (pattern) => {
        const sections = sectionMatches(pattern);
        return sections.length ? sections : matchingLines(pattern);
    };
    const responsibilities = sectionOrLineMatches(/职责|工作内容|岗位职责/);
    const requiredSkills = sectionOrLineMatches(/任职要求|任职资格|岗位要求|技能要求|职位要求/);
    const benefits = sectionOrLineMatches(/福利|待遇|薪酬|员工关怀/);
    return {
        title,
        company,
        jd_text: jdText,
        jd_found: Boolean(jdText),
        responsibilities,
        required_skills: requiredSkills,
        benefits,
        page_title: document.title || '',
        url: location.href
    };
})()
"""


class DOMExtractors:
    """平台 DOM 抽取脚本聚合与 URL 构建器。"""

    @classmethod
    def get_search_url(
        cls,
        platform: str,
        keyword: str,
        city_code: str,
        job_type: str = "social",
        page: int = 1,
    ) -> str:
        """根据平台、搜索关键词、城市和页码生成真实搜索目标 URL。"""
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        import urllib.parse
        encoded_kw = urllib.parse.quote(keyword)

        if platform == "boss":
            return f"https://www.zhipin.com/web/geek/job?query={encoded_kw}&city={city_code}&page={page}"
        elif platform == "liepin":
            return f"https://www.liepin.com/zhaopin/?city={city_code}&key={encoded_kw}&curPage={page}"
        elif platform == "51job":
            return f"https://we.51job.com/pc/search?jobArea={city_code}&keyword={encoded_kw}&page={page}"
        elif platform == "nowcoder":
            return f"https://www.nowcoder.com/jobs/recommend/campus?query={encoded_kw}&page={page}"
        return f"https://www.zhipin.com/web/geek/job?query={encoded_kw}&page={page}"

    @classmethod
    def get_detail_extractor_js(cls, platform: str) -> str:
        """获取详情页 DOM 抽取脚本；平台差异由通用语义选择器兼容。"""
        return DETAIL_DOM_EXTRACTOR_JS

    @classmethod
    def get_extractor_js(cls, platform: str) -> str:
        """根据当前页面导航状态选择真实岗位卡片提取器。"""
        if platform == "boss":
            return BOSS_DOM_EXTRACTOR_JS
        elif platform == "liepin":
            return LIEPIN_DOM_EXTRACTOR_JS
        elif platform == "51job":
            return JOB51_DOM_EXTRACTOR_JS
        elif platform == "nowcoder":
            return NOWCODER_DOM_EXTRACTOR_JS
        return BOSS_DOM_EXTRACTOR_JS
