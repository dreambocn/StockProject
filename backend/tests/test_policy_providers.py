import asyncio
from datetime import UTC, datetime

from app.core.settings import Settings
from app.integrations.policy_provider_registry import build_policy_provider_registry
from app.integrations.policy_providers.csrc_provider import (
    _parse_csrc_article_detail,
    _parse_csrc_list_payload,
)
from app.integrations.policy_providers.gov_cn_provider import (
    GovCnPolicyProvider,
    _parse_gov_cn_feed_payload,
)
from app.integrations.policy_providers.miit_provider import (
    _parse_miit_article_detail,
    _parse_miit_unit_payload,
)
from app.integrations.policy_providers.ndrc_provider import (
    _parse_ndrc_article_detail,
    _parse_ndrc_list_payload,
)
from app.integrations.policy_providers.npc_provider import (
    _parse_npc_article_detail,
    _parse_npc_list_payload,
)
from app.integrations.policy_providers.pbc_provider import (
    PbcPolicyProvider,
    _parse_pbc_article_detail,
    _parse_pbc_list_payload,
)


def test_gov_cn_provider_maps_title_and_url() -> None:
    async def run_test() -> None:
        async def fake_loader() -> list[dict[str, object]]:
            return [
                {
                    "title": "国务院关于推动人工智能产业创新发展的指导意见",
                    "url": "https://www.gov.cn/zhengce/content/2026-03/31/content_000001.htm",
                    "summary": "聚焦算力、数据与场景开放。",
                    "document_no": "国发〔2026〕8号",
                }
            ]

        provider = GovCnPolicyProvider(loader=fake_loader)

        documents = await provider.fetch_documents(
            now=datetime(2026, 3, 31, 10, 0, tzinfo=UTC)
        )

        assert len(documents) == 1
        assert documents[0].source == "gov_cn"
        assert documents[0].title == "国务院关于推动人工智能产业创新发展的指导意见"
        assert (
            documents[0].url
            == "https://www.gov.cn/zhengce/content/2026-03/31/content_000001.htm"
        )
        assert documents[0].issuing_authority == "国务院"

    asyncio.run(run_test())


def test_pbc_provider_extracts_published_at_and_authority() -> None:
    async def run_test() -> None:
        async def fake_loader() -> list[dict[str, object]]:
            return [
                {
                    "title": "中国人民银行召开货币政策委员会例会",
                    "url": "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/543210/index.html",
                    "published_at": "2026-03-30T09:30:00+08:00",
                    "summary": "强调保持流动性合理充裕。",
                }
            ]

        provider = PbcPolicyProvider(loader=fake_loader)

        documents = await provider.fetch_documents(
            now=datetime(2026, 3, 31, 10, 0, tzinfo=UTC)
        )

        assert len(documents) == 1
        assert documents[0].issuing_authority == "中国人民银行"
        assert documents[0].published_at == datetime(2026, 3, 30, 1, 30, tzinfo=UTC)

    asyncio.run(run_test())


def test_policy_provider_registry_respects_enabled_settings() -> None:
    settings = Settings(
        _env_file=None,
        policy_provider_gov_cn_enabled=True,
        policy_provider_npc_enabled=False,
        policy_provider_pbc_enabled=True,
        policy_provider_csrc_enabled=False,
        policy_provider_ndrc_enabled=False,
        policy_provider_miit_enabled=False,
    )

    providers = build_policy_provider_registry(settings)

    assert [provider.source for provider in providers] == ["gov_cn", "pbc"]


def test_parse_gov_cn_feed_payload_extracts_official_rows() -> None:
    payload = """
    [
      {
        "TITLE": "全国农业普查条例",
        "SUB_TITLE": "",
        "URL": "https://www.gov.cn/zhengce/content/202603/content_7063863.htm",
        "DOCRELPUBTIME": "2026-03-26"
      },
      {
        "TITLE": "中共中央办公厅 国务院办公厅关于加快建立长期护理保险制度的意见",
        "SUB_TITLE": "支持长期护理保险制度建设。",
        "URL": "https://www.gov.cn/zhengce/202603/content_7063790.htm",
        "DOCRELPUBTIME": "2026-03-25"
      }
    ]
    """

    rows = _parse_gov_cn_feed_payload(payload)

    assert len(rows) == 2
    assert rows[0]["title"] == "全国农业普查条例"
    assert rows[0]["url"] == "https://www.gov.cn/zhengce/content/202603/content_7063863.htm"
    assert rows[0]["published_at"] == "2026-03-26T00:00:00+08:00"
    assert rows[1]["summary"] == "支持长期护理保险制度建设。"


def test_parse_pbc_list_payload_extracts_policy_articles() -> None:
    payload = """
    <div class="list">
      <a href="/tiaofasi/144941/3581332/2026032016195944841/index.html">
        中国人民银行 国家外汇管理局关于印发《境内企业境外放款管理办法》的通知（银发〔2026〕63号）
      </a>
      <a href="/tiaofasi/144941/3581332/2026031817003226287/index.html">
        中国人民银行 国家金融监督管理总局公告〔2026〕第5号
      </a>
    </div>
    """

    rows = _parse_pbc_list_payload(payload)

    assert len(rows) == 2
    assert rows[0]["title"].startswith("中国人民银行 国家外汇管理局")
    assert rows[0]["url"] == "https://www.pbc.gov.cn/tiaofasi/144941/3581332/2026032016195944841/index.html"
    assert rows[1]["url"] == "https://www.pbc.gov.cn/tiaofasi/144941/3581332/2026031817003226287/index.html"


def test_parse_pbc_article_detail_extracts_meta_and_attachments() -> None:
    payload = """
    <html>
      <head>
        <meta name="ArticleTitle" content="中国人民银行 国家外汇管理局关于印发《境内企业境外放款管理办法》的通知（银发〔2026〕63号）">
        <meta name="PubDate" content="2026-03-20">
        <meta name="Description" content="附1参数设置.pdf 附2境外放款业务登记申请表.pdf。">
      </head>
      <body>
        <span id="shijian">2026-03-20 17:30:00</span>
        <div class="content">
          <p>中国人民银行、国家外汇管理局决定印发本办法。</p>
          <p><a href="/tiaofasi/144941/file/202603/P020260320000001.pdf">附1参数设置.pdf</a></p>
          <p><a href="https://www.pbc.gov.cn/tiaofasi/144941/file/202603/P020260320000002.pdf">附2境外放款业务登记申请表.pdf</a></p>
        </div>
      </body>
    </html>
    """

    row = _parse_pbc_article_detail(
        payload,
        url="https://www.pbc.gov.cn/tiaofasi/144941/3581332/2026032016195944841/index.html",
    )

    assert row["title"].startswith("中国人民银行 国家外汇管理局")
    assert row["published_at"] == "2026-03-20T17:30:00+08:00"
    assert row["document_no"] == "银发〔2026〕63号"
    assert row["summary"] == "附1参数设置.pdf 附2境外放款业务登记申请表.pdf。"
    assert row["attachment_urls"] == [
        "https://www.pbc.gov.cn/tiaofasi/144941/file/202603/P020260320000001.pdf",
        "https://www.pbc.gov.cn/tiaofasi/144941/file/202603/P020260320000002.pdf",
    ]


def test_parse_ndrc_list_payload_extracts_notice_articles() -> None:
    payload = """
    <a href="./202603/t20260327_1404395.html">关于优化完善无线电频率占用费标准的通知(发改价格〔2026〕413号)</a>
    <a href="../../jd/jd/202603/t20260317_1404204.html">两部门联合印发意见全面推进儿童友好建设</a>
    <a href="./202602/t20260213_1403763.html">关于加强投资项目在线审批监管平台和工程建设项目审批管理系统数据共享的通知(发改办投资〔2026〕88号)</a>
    """

    rows = _parse_ndrc_list_payload(payload)

    assert len(rows) == 2
    assert rows[0]["title"].startswith("关于优化完善无线电频率占用费标准的通知")
    assert rows[0]["url"] == "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202603/t20260327_1404395.html"
    assert rows[1]["url"] == "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202602/t20260213_1403763.html"


def test_parse_ndrc_article_detail_extracts_meta_fields() -> None:
    payload = """
    <meta name="ArticleTitle" content="关于优化完善无线电频率占用费标准的通知(发改价格〔2026〕413号)">
    <meta name="PubDate" content="2026-03-27 15:02:08">
    <meta name="ContentSource" content="价格司">
    <div class="TRS_Editor">
      <p>为进一步规范无线电频率资源使用管理，现就有关事项通知如下。</p>
      <p><a href="./P020260327000001.pdf">附件：无线电频率占用费标准表.pdf</a></p>
    </div>
    """

    row = _parse_ndrc_article_detail(
        payload,
        url="https://www.ndrc.gov.cn/xxgk/zcfb/tz/202603/t20260327_1404395.html",
    )

    assert row["title"].startswith("关于优化完善无线电频率占用费标准的通知")
    assert row["published_at"] == "2026-03-27T15:02:08+08:00"
    assert row["issuing_authority"] == "国家发展改革委"
    assert row["document_no"] == "发改价格〔2026〕413号"
    assert row["attachment_urls"] == [
        "https://www.ndrc.gov.cn/xxgk/zcfb/tz/202603/P020260327000001.pdf"
    ]


def test_parse_miit_unit_payload_extracts_notice_articles() -> None:
    payload = """
    {
      "success": true,
      "data": {
        "html": "<li class=\\"cf\\"><a class=\\"fl\\" href=\\"/jgsj/kjs/wjfb/art/2026/art_fa114cdc2d804006bca3116e0253b37e.html\\" title=\\"工业和信息化部关于公布第七批产业技术基础公共服务平台名单的通知\\">工业和信息化部关于公布第七批产业技术基础公共服务平台名单的通知</a><span class=\\"fr\\">2026-03-31</span></li><li class=\\"cf\\"><a class=\\"fl\\" href=\\"/jgsj/kjs/wjfb/art/2026/art_c66a966b86904ff286b49faddf937974.html\\" title=\\"工业和信息化部关于印发《工业产品质量控制和技术评价实验室管理办法》的通知\\">工业和信息化部关于印发《工业产品质量控制和技术评价实验室管理办法》的通知</a><span class=\\"fr\\">2026-03-31</span></li>"
      }
    }
    """

    rows = _parse_miit_unit_payload(payload)

    assert len(rows) == 2
    assert rows[0]["title"] == "工业和信息化部关于公布第七批产业技术基础公共服务平台名单的通知"
    assert rows[0]["url"] == "https://www.miit.gov.cn/jgsj/kjs/wjfb/art/2026/art_fa114cdc2d804006bca3116e0253b37e.html"
    assert rows[0]["published_at"] == "2026-03-31T00:00:00+08:00"


def test_parse_miit_article_detail_extracts_meta_fields() -> None:
    payload = """
    <meta name="ArticleTitle" content="工业和信息化部关于公布第七批产业技术基础公共服务平台名单的通知">
    <meta name="PubDate" content="2026-03-31 16:15">
    <meta name="ContentSource" content="科技司">
    <meta name="Description" content="为进一步提升产业技术基础公共服务能力和水平，现予以公布。">
    <a href="/jgsj/kjs/wjfb/attach/P020260331000001.pdf">附件：平台名单.pdf</a>
    """

    row = _parse_miit_article_detail(
        payload,
        url="https://www.miit.gov.cn/jgsj/kjs/wjfb/art/2026/art_fa114cdc2d804006bca3116e0253b37e.html",
    )

    assert row["title"] == "工业和信息化部关于公布第七批产业技术基础公共服务平台名单的通知"
    assert row["published_at"] == "2026-03-31T16:15:00+08:00"
    assert row["summary"] == "为进一步提升产业技术基础公共服务能力和水平，现予以公布。"
    assert row["attachment_urls"] == [
        "https://www.miit.gov.cn/jgsj/kjs/wjfb/attach/P020260331000001.pdf"
    ]


def test_parse_csrc_list_payload_keeps_policy_titles() -> None:
    payload = """
    <a href="/csrc/c100028/c1615676/content.shtml">国务院公布《国务院关于进一步贯彻实施〈中华人民共和国行政处罚法〉的通知》</a>
    <a href="/csrc/c100028/c1605899/content.shtml">陈华平任深圳证券交易所党委书记</a>
    <a href="/csrc/c100028/c1603534/content.shtml">证监会就《证券期货行政执法当事人承诺制度实施规定（征求意见稿）》公开征求意见</a>
    """

    rows = _parse_csrc_list_payload(payload)

    assert len(rows) == 2
    assert rows[0]["url"] == "https://www.csrc.gov.cn/csrc/c100028/c1615676/content.shtml"
    assert rows[1]["title"].startswith("证监会就《证券期货行政执法当事人承诺制度实施规定")


def test_parse_csrc_article_detail_extracts_meta_fields() -> None:
    payload = """
    <meta name="ArticleTitle" content="证监会就《证券期货行政执法当事人承诺制度实施规定（征求意见稿）》公开征求意见"/>
    <meta name="PubDate" content="2025-10-12 22:42:52"/>
    <meta name="ContentSource" content="中国证监会"/>
    <meta name="Description" content="为贯彻落实党中央、国务院决策部署和《证券法》要求，现向社会公开征求意见。"/>
    """

    row = _parse_csrc_article_detail(
        payload,
        url="https://www.csrc.gov.cn/csrc/c100028/c1603534/content.shtml",
    )

    assert row["title"].startswith("证监会就《证券期货行政执法当事人承诺制度实施规定")
    assert row["published_at"] == "2025-10-12T22:42:52+08:00"
    assert row["issuing_authority"] == "中国证监会"
    assert row["summary"] == "为贯彻落实党中央、国务院决策部署和《证券法》要求，现向社会公开征求意见。"


def test_parse_npc_list_payload_extracts_law_articles() -> None:
    payload = """
    <a href="../../c30834/202603/t20260313_453201.html">中华人民共和国民族团结进步促进法</a>
    <a href="../../kgfb/202603/t20260312_453178.html">中华人民共和国主席令（第七十三号）</a>
    <a href="https://www.news.cn/politics/20260313/f2d746f769ee4cb9a97e2f8cfb15783e/c.html">中华人民共和国生态环境法典</a>
    """

    rows = _parse_npc_list_payload(payload)

    assert len(rows) == 2
    assert rows[0]["url"] == "http://www.npc.gov.cn/npc/c2/c30834/202603/t20260313_453201.html"
    assert rows[1]["title"] == "中华人民共和国主席令（第七十三号）"


def test_parse_npc_article_detail_extracts_source_date_and_content() -> None:
    payload = """
    <div class="tit"><h1>中华人民共和国民族团结进步促进法</h1></div>
    <div class="fontsize"> 来源： 新华网<span class="fr" id="zzrq"></span></div>
    <script type="text/javascript">
        var fbrq = "2026年03月13日 08:16"
        if($('#zzrq').html() == ''){
            $('#zzrq').html(fbrq);
        }
    </script>
    <div id="Zoom">
      <div class="TRS_Editor">
        <div>新华社北京3月12日电</div>
        <div>中华人民共和国民族团结进步促进法</div>
      </div>
    </div>
    """

    row = _parse_npc_article_detail(
        payload,
        url="http://www.npc.gov.cn/npc/c2/c30834/202603/t20260313_453201.html",
    )

    assert row["title"] == "中华人民共和国民族团结进步促进法"
    assert row["published_at"] == "2026-03-13T08:16:00+08:00"
    assert row["summary"] == "新华社北京3月12日电 中华人民共和国民族团结进步促进法"
    assert row["content_text"] == "新华社北京3月12日电 中华人民共和国民族团结进步促进法"
