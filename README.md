```
    ____       _       __     __    ______
   / __ \__  _| |     / /__  / /_  / ____/___  ____  __  __
  / /_/ / / / / | /| / / _ \/ __ \/ /   / __ \/ __ \/ / / /
 / ____/ /_/ /| |/ |/ /  __/ /_/ / /___/ /_/ / /_/ / /_/ /
/_/    \__, / |__/|__/\___/_.___/\____/\____/ .___/\__, /
      /____/                               /_/    /____/
```

PyWebCopy is a free tool for copying full or partial websites locally
onto your hard-disk for offline viewing.

PyWebCopy will scan the specified website and download its content onto your hard-disk.
Links to resources such as style-sheets, images, and other pages in the website
will automatically be remapped to match the local path.
Using its extensive configuration you can define which parts of a website will be copied and how.

## What can PyWebCopy do?

PyWebCopy will examine the HTML mark-up of a website and attempt to discover all linked resources
such as other pages, images, videos, file downloads - anything and everything.
It will download all of theses resources, and continue to search for more.
In this manner, WebCopy can "crawl" an entire website and download everything it sees
in an effort to create a reasonable facsimile of the source website.

## What can PyWebCopy not do?

PyWebCopy does not include a virtual DOM or any form of JavaScript parsing.
If a website makes heavy use of JavaScript to operate, it is unlikely PyWebCopy will be able
to make a true copy if it is unable to discover all of the website due to
JavaScript being used to dynamically generate links.

PyWebCopy does not download the raw source code of a web site,
it can only download what the HTTP server returns.
While it will do its best to create an offline copy of a website,
advanced data driven websites may not work as expected once they have been copied.
