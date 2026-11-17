"""A minimal in-memory stand-in for the parts of a boto3 S3 client that lasrc_ancillary uses."""

import io
from typing import Any


class FakeS3:
    def __init__(self, objects: dict[str, bytes], page_size: int = 1000):
        self.objects = objects
        self.page_size = page_size
        self.get_calls: list[dict[str, Any]] = []

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = kwargs.get("Prefix", "")
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        start = int(kwargs.get("ContinuationToken", 0))
        page = keys[start : start + self.page_size]
        result: dict[str, Any] = {"KeyCount": len(page)}
        if page:
            result["Contents"] = [
                {"Key": k, "Size": len(self.objects[k])} for k in page
            ]
        if start + self.page_size < len(keys):
            result["IsTruncated"] = True
            result["NextContinuationToken"] = str(start + self.page_size)
        else:
            result["IsTruncated"] = False
        return result

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.get_calls.append(kwargs)
        key = kwargs["Key"]
        if key not in self.objects:
            raise KeyError(key)
        data = self.objects[key]
        rng = kwargs.get("Range")
        if rng:
            first, _, last = rng.removeprefix("bytes=").partition("-")
            data = data[int(first) : int(last) + 1 if last else None]
        return {"Body": io.BytesIO(data)}
