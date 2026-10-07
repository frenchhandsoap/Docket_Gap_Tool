# Docket Gap Tool v0.4.2

This version fixes generic wrapper ZIP folders such as `New folder (3)`. If your downloaded documents ZIP contains subfolders inside a generic parent folder, the tool now matches against the real inner case folders instead of the outer wrapper.

# Docket Gap Tool - fixed Word-doc package (v0.4.1)

This fixed package supports docket sources in:

- `input/docket_pdfs/` for browser-saved PDF docket printouts
- `input/docket_texts/` for `.txt` docket exports
- `input/docket_word_docs/` for `.docx` Word docket exports

## Important Windows fix

If you previously unzipped an older package, delete the old folder completely first. Do **not** merge/extract this ZIP over the old folder. Then unzip this package fresh and run `RUN_ME_WINDOWS.bat`.

The previous error:

`ModuleNotFoundError: No module named 'docket_gap_tool.docx_import'`

means the old extracted folder was missing the Word-import module. This v0.4.1 package includes it and the runner checks for it before installing.

## Quick run

1. Put your downloaded-document ZIP in `input/downloaded_artifacts/`.
2. Put Word docket exports in `input/docket_word_docs/`, or docket PDFs in `input/docket_pdfs/`, or docket text in `input/docket_texts/`.
3. Double-click `RUN_ME_WINDOWS.bat`.
4. Open `output/docket_gap_download_request_by_case.xlsx`.

If the downloaded-document ZIP is very large, use the separate inventory scanner package instead and upload its small output bundle to ChatGPT.


## v0.4.3 fix

This version fixes downloaded-artifact matching when your downloaded ZIP contains case ZIPs inside a generic parent folder, for example:

```text
New folder (3).zip
  New folder (3)/
    Akorn, Inc..zip
    Chinos Holdings.zip
```

The tool now opens those nested case ZIPs and inventories the PDFs inside them instead of treating `New folder (3)` as the case folder or misreading `(3)` as docket entry 3.
