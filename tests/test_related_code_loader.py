from mr_auto_reviewer.models import Change
from mr_auto_reviewer.related_code_loader import RelatedCodeLoader


def test_related_code_loader_loads_changed_and_imported_java_files():
    files = {
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java": """
package com.sohu.mainstay.loki.service.channel.action.assemble.news;

import com.sohu.mainstay.loki.service.channel.loader.DanubeNewsLoader;

public class GenericFieldReplaceAssembleService {
    private DanubeNewsLoader danubeNewsLoader;
}
""".strip(),
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/loader/DanubeNewsLoader.java": """
package com.sohu.mainstay.loki.service.channel.loader;

import com.sohu.mainstay.loki.service.channel.model.NewsItem;

public class DanubeNewsLoader {
    public NewsItem load() { return null; }
}
""".strip(),
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/model/NewsItem.java": """
package com.sohu.mainstay.loki.service.channel.model;

public class NewsItem {}
""".strip(),
    }

    loader = RelatedCodeLoader(
        file_loader=lambda path, ref: files.get(path),
        max_context_files=4,
        max_depth=2,
        max_file_chars=400,
    )

    contexts = loader.load(
        changes=[
            Change(
                new_path="service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java",
                diff="+ private DanubeNewsLoader danubeNewsLoader;",
            )
        ],
        ref="head-sha",
    )

    assert [item.path for item in contexts] == [
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java",
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/loader/DanubeNewsLoader.java",
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/model/NewsItem.java",
    ]
    assert [item.depth for item in contexts] == [0, 1, 2]


def test_related_code_loader_limits_total_files():
    files = {
        "src/a.py": "import b\nimport c\nimport d\n",
        "b.py": "value = 1",
        "c.py": "value = 2",
        "d.py": "value = 3",
    }

    loader = RelatedCodeLoader(
        file_loader=lambda path, ref: files.get(path),
        max_context_files=2,
        max_depth=2,
        max_file_chars=200,
    )

    contexts = loader.load(
        changes=[Change(new_path="src/a.py", diff="+import b")],
        ref="head-sha",
    )

    assert len(contexts) == 2


def test_related_code_loader_uses_path_resolver_when_direct_import_path_is_missing():
    files = {
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java": """
package com.sohu.mainstay.loki.service.channel.action.assemble.news;

import com.sohu.mainstay.loki.common.loader.DanubeNewsLoader;

public class GenericFieldReplaceAssembleService {}
""".strip(),
        "common/src/main/java/com/sohu/mainstay/loki/common/loader/DanubeNewsLoader.java": """
package com.sohu.mainstay.loki.common.loader;

public class DanubeNewsLoader {}
""".strip(),
    }
    resolutions = {
        "service-channel/src/main/java/com/sohu/mainstay/loki/common/loader/DanubeNewsLoader.java": [
            "common/src/main/java/com/sohu/mainstay/loki/common/loader/DanubeNewsLoader.java"
        ]
    }

    loader = RelatedCodeLoader(
        file_loader=lambda path, ref: files.get(path),
        path_resolver=lambda path, ref: resolutions.get(path, []),
        max_context_files=3,
        max_depth=2,
        max_file_chars=400,
    )

    contexts = loader.load(
        changes=[
            Change(
                new_path="service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java",
                diff="+ import com.sohu.mainstay.loki.common.loader.DanubeNewsLoader;",
            )
        ],
        ref="head-sha",
    )

    assert [item.path for item in contexts] == [
        "service-channel/src/main/java/com/sohu/mainstay/loki/service/channel/action/assemble/news/GenericFieldReplaceAssembleService.java",
        "common/src/main/java/com/sohu/mainstay/loki/common/loader/DanubeNewsLoader.java",
    ]
