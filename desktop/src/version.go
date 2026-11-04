package main

import (
	"regexp"
	"strconv"
	"strings"
)

// Keep ordering aligned with octop.infra.setup.self_update.parse_version.
// Local segments (+local) are parsed but ignored, matching the Python key.

var pep440RE = regexp.MustCompile(`(?i)^v?(?:(?P<epoch>\d+)!)?(?P<release>\d+(?:\.\d+)*)(?:[-_\.]?(?P<pre_l>alpha|a|beta|b|preview|pre|rc|c)[-_\.]?(?P<pre_n>\d+)?)?(?:(?:[-_\.]?(?P<post_l>post|rev|r)[-_\.]?(?P<post_n>\d+))|(?:-(?P<post_n1>\d+)))?(?:[-_\.]?(?P<dev_l>dev)[-_\.]?(?P<dev_n>\d+)?)?(?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?$`)

var preRank = map[string]int{
	"a": 0, "alpha": 0,
	"b": 1, "beta": 1,
	"c": 2, "rc": 2, "pre": 2, "preview": 2,
}

const releasePad = 8

type versionKey struct {
	epoch   int
	release [releasePad]int
	pre     []int
	post    int
	dev     []int
}

func compareVersions(left, right string) int {
	a := parseVersion(left)
	b := parseVersion(right)
	if a.epoch != b.epoch {
		return cmpInt(a.epoch, b.epoch)
	}
	for i := 0; i < releasePad; i++ {
		if a.release[i] != b.release[i] {
			return cmpInt(a.release[i], b.release[i])
		}
	}
	if c := compareIntSlice(a.pre, b.pre); c != 0 {
		return c
	}
	if a.post != b.post {
		return cmpInt(a.post, b.post)
	}
	return compareIntSlice(a.dev, b.dev)
}

func parseVersion(value string) versionKey {
	value = strings.TrimSpace(value)
	match := pep440RE.FindStringSubmatch(value)
	if match == nil {
		return numericVersionKey(value)
	}
	get := subexpGetter(pep440RE, match)
	key := versionKey{}
	if epoch := get("epoch"); epoch != "" {
		key.epoch, _ = strconv.Atoi(epoch)
	}
	for i, part := range strings.Split(get("release"), ".") {
		if i >= releasePad {
			break
		}
		key.release[i], _ = strconv.Atoi(part)
	}
	preL := strings.ToLower(get("pre_l"))
	devL := get("dev_l")
	if preL != "" {
		n := 0
		if raw := get("pre_n"); raw != "" {
			n, _ = strconv.Atoi(raw)
		}
		key.pre = []int{0, preRank[preL], n}
	} else if devL != "" {
		key.pre = []int{-1}
	} else {
		key.pre = []int{1}
	}
	if raw := get("post_n"); raw != "" {
		key.post, _ = strconv.Atoi(raw)
	} else if raw := get("post_n1"); raw != "" {
		key.post, _ = strconv.Atoi(raw)
	} else {
		key.post = -1
	}
	if devL != "" {
		n := 0
		if raw := get("dev_n"); raw != "" {
			n, _ = strconv.Atoi(raw)
		}
		key.dev = []int{0, n}
	} else {
		key.dev = []int{1}
	}
	return key
}

func numericVersionKey(value string) versionKey {
	key := versionKey{pre: []int{1}, post: -1, dev: []int{1}}
	parts := strings.Split(value, ".")
	if len(parts) == 0 {
		parts = []string{""}
	}
	for i, segment := range parts {
		if i >= releasePad {
			break
		}
		numeric := ""
		for _, ch := range segment {
			if ch < '0' || ch > '9' {
				break
			}
			numeric += string(ch)
		}
		if numeric != "" {
			key.release[i], _ = strconv.Atoi(numeric)
		}
	}
	return key
}

func subexpGetter(re *regexp.Regexp, match []string) func(string) string {
	names := re.SubexpNames()
	return func(name string) string {
		for i, n := range names {
			if n == name {
				return match[i]
			}
		}
		return ""
	}
}

func compareIntSlice(left, right []int) int {
	n := min(len(left), len(right))
	for i := 0; i < n; i++ {
		if c := cmpInt(left[i], right[i]); c != 0 {
			return c
		}
	}
	return cmpInt(len(left), len(right))
}

func cmpInt(left, right int) int {
	if left < right {
		return -1
	}
	if left > right {
		return 1
	}
	return 0
}
